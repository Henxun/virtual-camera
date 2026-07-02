#include "akvc/core_native/frame_types.h"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <mutex>
#include <optional>
#include <string>
#include <thread>

namespace akvc::core_native {

namespace {

constexpr std::int32_t PREVIEW_WIDTH = 320;
constexpr std::int32_t PREVIEW_HEIGHT = 180;
constexpr std::int32_t DEFAULT_PROVIDER_WIDTH = 1280;
constexpr std::int32_t DEFAULT_PROVIDER_HEIGHT = 720;
constexpr std::int32_t DEFAULT_PROVIDER_FPS = 30;

std::string render_preview_rgb(const Frame& frame) {
    if (frame.fourcc != FOURCC_RGB24 || frame.width <= 0 || frame.height <= 0) {
        return {};
    }

    const auto src = frame.data.unchecked<1>();
    const auto expected = static_cast<py::ssize_t>(frame.width) * frame.height * 3;
    if (src.size() < expected) {
        return {};
    }

    std::string out(static_cast<std::size_t>(PREVIEW_WIDTH) * PREVIEW_HEIGHT * 3, '\0');
    auto* dst = reinterpret_cast<std::uint8_t*>(out.data());
    for (std::int32_t y = 0; y < PREVIEW_HEIGHT; ++y) {
        const std::int32_t src_y = (y * frame.height) / PREVIEW_HEIGHT;
        for (std::int32_t x = 0; x < PREVIEW_WIDTH; ++x) {
            const std::int32_t src_x = (x * frame.width) / PREVIEW_WIDTH;
            const auto src_idx = (static_cast<std::size_t>(src_y) * frame.width + src_x) * 3;
            const auto dst_idx = (static_cast<std::size_t>(y) * PREVIEW_WIDTH + x) * 3;
            dst[dst_idx + 0] = src(src_idx + 2);
            dst[dst_idx + 1] = src(src_idx + 1);
            dst[dst_idx + 2] = src(src_idx + 0);
        }
    }
    return out;
}

}  // namespace

class NativeRuntimeHost {
public:
    NativeRuntimeHost() = default;

    ~NativeRuntimeHost() {
        try {
            stop();
        } catch (...) {
        }
    }

    void start(py::object provider, py::object pipeline, py::object sink_factory) {
        stop();
        {
            std::scoped_lock lock(state_mu_);
            frames_published_ = 0;
            frames_dropped_ = 0;
            consumer_count_ = 0;
            fps_ = 0.0;
            last_error_.clear();
            last_preview_.clear();
            running_ = true;
        }
        stop_requested_.store(false);
        provider_ = std::move(provider);
        pipeline_ = std::move(pipeline);
        sink_factory_ = std::move(sink_factory);
        source_id_.clear();
        worker_ = std::thread([this]() { run_loop(); });
    }

    void start_source(const std::string& source_id) {
        stop();
        {
            std::scoped_lock lock(state_mu_);
            frames_published_ = 0;
            frames_dropped_ = 0;
            consumer_count_ = 0;
            fps_ = 0.0;
            last_error_.clear();
            last_preview_.clear();
            running_ = true;
        }
        stop_requested_.store(false);
        provider_ = py::none();
        pipeline_ = py::none();
        sink_factory_ = py::none();
        source_id_ = source_id;
        worker_ = std::thread([this]() { run_native_source_loop(); });
    }

    void stop() {
        stop_requested_.store(true);
        request_provider_stop();
        if (worker_.joinable()) {
            {
                py::gil_scoped_release release;
                worker_.join();
            }
        }
        source_id_.clear();
    }

    py::dict snapshot() const {
        std::scoped_lock lock(state_mu_);
        py::dict out;
        out["running"] = py::bool_(running_);
        out["fps"] = py::float_(fps_);
        out["frames_published"] = py::int_(frames_published_);
        out["frames_dropped"] = py::int_(frames_dropped_);
        out["consumer_count"] = py::int_(consumer_count_);
        out["last_error"] = last_error_.empty() ? py::object(py::none()) : py::object(py::str(last_error_));
        out["last_preview"] = last_preview_.empty() ? py::object(py::none()) : py::object(py::bytes(last_preview_));
        return out;
    }

private:
    void run_loop() {
        try {
            {
                py::gil_scoped_acquire gil;
                provider_.attr("open")();
                sink_ = sink_factory_();
                sink_.attr("open")();
            }
            auto last_metrics_t = std::chrono::steady_clock::now();
            auto last_preview_t = std::chrono::steady_clock::time_point{};
            std::uint64_t published_window = 0;

            while (!stop_requested_.load()) {
                py::gil_scoped_acquire gil;
                py::object frame_obj = provider_.attr("read")();
                if (stop_requested_.load()) {
                    break;
                }

                Frame frame = frame_obj.cast<Frame>();
                const auto now = std::chrono::steady_clock::now();
                if (last_preview_t.time_since_epoch().count() == 0 ||
                    now - last_preview_t >= std::chrono::milliseconds(200)) {
                    last_preview_t = now;
                    const auto preview = render_preview_rgb(frame);
                    if (!preview.empty()) {
                        std::scoped_lock lock(state_mu_);
                        last_preview_ = preview;
                    }
                }

                py::object processed_obj = pipeline_.attr("process")(frame_obj);
                if (stop_requested_.load()) {
                    break;
                }

                try {
                    sink_.attr("publish")(processed_obj);
                    const int consumers = py::int_(sink_.attr("consumer_count"));
                    {
                        std::scoped_lock lock(state_mu_);
                        ++frames_published_;
                        consumer_count_ = consumers;
                    }
                    ++published_window;
                } catch (const py::error_already_set& exc) {
                    {
                        std::scoped_lock lock(state_mu_);
                        ++frames_dropped_;
                        last_error_ = py::str(exc.value()).cast<std::string>();
                    }
                }

                const auto elapsed = std::chrono::duration<double>(now - last_metrics_t).count();
                if (elapsed >= 0.5) {
                    std::scoped_lock lock(state_mu_);
                    fps_ = static_cast<double>(published_window) / elapsed;
                    published_window = 0;
                    last_metrics_t = now;
                }
            }
        } catch (const py::error_already_set& exc) {
            std::scoped_lock lock(state_mu_);
            last_error_ = exc.what();
        } catch (const std::exception& exc) {
            std::scoped_lock lock(state_mu_);
            last_error_ = exc.what();
        }

        close_objects();
        std::scoped_lock lock(state_mu_);
        running_ = false;
    }

    void run_native_source_loop() {
        try {
            {
                py::gil_scoped_acquire gil;
                py::module_ native = py::module_::import("akvc._core_native");
                py::dict parsed = native.attr("parse_source_id").cast<py::function>()(source_id_).cast<py::dict>();
                const std::string kind = py::str(parsed["kind"]).cast<std::string>();

                if (kind == "usb") {
                    const std::int32_t device_index = py::int_(parsed["device_index"]).cast<std::int32_t>();
                    provider_ = native.attr("NativeUsbCaptureOpener")(DEFAULT_PROVIDER_WIDTH, DEFAULT_PROVIDER_HEIGHT, DEFAULT_PROVIDER_FPS)
                        .attr("open")(device_index, std::string("msmf"));
                } else {
                    std::string pattern = "colorbar";
                    if (!parsed["pattern_id"].is_none()) {
                        pattern = py::str(parsed["pattern_id"]).cast<std::string>();
                    }
                    provider_ = native.attr("NativeTestPatternProvider")(DEFAULT_PROVIDER_WIDTH, DEFAULT_PROVIDER_HEIGHT, DEFAULT_PROVIDER_FPS, pattern);
                    provider_.attr("open")();
                }

                source_producer_ = native.attr("NativeWindowsFrameBusProducer")();
                source_producer_.attr("open")();
                source_regulator_ = native.attr("NativeFpsRegulator")(30.0, 10.0);
            }

            auto last_metrics_t = std::chrono::steady_clock::now();
            auto last_preview_t = std::chrono::steady_clock::time_point{};
            std::uint64_t published_window = 0;

            while (!stop_requested_.load()) {
                const auto now = std::chrono::steady_clock::now();
                int consumers = 0;

                try {
                    py::gil_scoped_acquire gil;
                    py::object frame_obj = provider_.attr("read")();
                    if (stop_requested_.load()) {
                        break;
                    }

                    Frame frame = frame_obj.cast<Frame>();
                    if (last_preview_t.time_since_epoch().count() == 0 ||
                        now - last_preview_t >= std::chrono::milliseconds(200)) {
                        last_preview_t = now;
                        const auto preview = render_preview_rgb(frame);
                        if (!preview.empty()) {
                            std::scoped_lock lock(state_mu_);
                            last_preview_ = preview;
                        }
                    }

                    Frame resized = resize_rgb24_frame(frame, 1280, 720);
                    py::object regulated_obj = source_regulator_.attr("process")(py::cast(resized));
                    if (stop_requested_.load()) {
                        break;
                    }

                    Frame regulated = regulated_obj.cast<Frame>();
                    Frame nv12 = rgb24_to_nv12_frame(regulated);
                    source_producer_.attr("publish")(py::cast(nv12));
                    consumers = py::int_(source_producer_.attr("consumer_count"));
                } catch (const py::error_already_set& exc) {
                    std::scoped_lock lock(state_mu_);
                    ++frames_dropped_;
                    last_error_ = exc.what();
                    continue;
                }

                {
                    std::scoped_lock lock(state_mu_);
                    ++frames_published_;
                    consumer_count_ = consumers;
                }
                ++published_window;

                const auto elapsed = std::chrono::duration<double>(now - last_metrics_t).count();
                if (elapsed >= 0.5) {
                    std::scoped_lock lock(state_mu_);
                    fps_ = static_cast<double>(published_window) / elapsed;
                    published_window = 0;
                    last_metrics_t = now;
                }
            }
        } catch (const py::error_already_set& exc) {
            std::scoped_lock lock(state_mu_);
            last_error_ = exc.what();
        } catch (const std::exception& exc) {
            std::scoped_lock lock(state_mu_);
            last_error_ = exc.what();
        }

        close_objects();
        std::scoped_lock lock(state_mu_);
        running_ = false;
    }

    void request_provider_stop() {
        if (provider_.is_none()) {
            return;
        }
        py::gil_scoped_acquire gil;
        try {
            provider_.attr("request_stop")();
        } catch (const py::error_already_set&) {
        }
    }

    void close_objects() {
        py::gil_scoped_acquire gil;
        if (!source_producer_.is_none()) {
            try {
                source_producer_.attr("close")();
            } catch (const py::error_already_set&) {
            }
            source_producer_ = py::none();
        }
        source_regulator_ = py::none();
        if (!sink_.is_none()) {
            try {
                sink_.attr("close")();
            } catch (const py::error_already_set&) {
            }
            sink_ = py::none();
        }
        if (!provider_.is_none()) {
            try {
                provider_.attr("close")();
            } catch (const py::error_already_set&) {
            }
        }
    }

    mutable std::mutex state_mu_;
    std::thread worker_;
    std::atomic<bool> stop_requested_{false};
    bool running_ = false;
    double fps_ = 0.0;
    std::uint64_t frames_published_ = 0;
    std::uint64_t frames_dropped_ = 0;
    int consumer_count_ = 0;
    std::string last_error_;
    std::string last_preview_;
    py::object provider_ = py::none();
    py::object pipeline_ = py::none();
    py::object sink_factory_ = py::none();
    py::object sink_ = py::none();
    py::object source_producer_ = py::none();
    py::object source_regulator_ = py::none();
    std::string source_id_;
};

void bind_runtime_host(py::module_& m) {
    py::class_<NativeRuntimeHost>(m, "NativeRuntimeHost")
        .def(py::init<>())
        .def("start", &NativeRuntimeHost::start, py::arg("provider"), py::arg("pipeline"), py::arg("sink_factory"))
        .def("start_source", &NativeRuntimeHost::start_source, py::arg("source_id"))
        .def("stop", &NativeRuntimeHost::stop)
        .def("snapshot", &NativeRuntimeHost::snapshot);
}

}  // namespace akvc::core_native
