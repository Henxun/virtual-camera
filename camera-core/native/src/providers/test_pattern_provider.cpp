#include "akvc/core_native/frame_types.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <string>
#include <thread>

namespace akvc::core_native {

class NativeTestPatternProvider {
public:
    NativeTestPatternProvider(
        std::int32_t width,
        std::int32_t height,
        std::int32_t fps,
        const std::string& pattern)
        : width_(width),
          height_(height),
          fps_(fps),
          pattern_(pattern),
          frame_period_(1.0 / static_cast<double>(fps)) {}

    void open() {
        stop_requested_ = false;
        next_t_ = std::chrono::steady_clock::now();
        opened_ = true;
    }

    Frame read() {
        if (!opened_) {
            if (stop_requested_) {
                return stop_frame();
            }
            open();
        }
        if (stop_requested_) {
            return stop_frame();
        }

        const auto now = std::chrono::steady_clock::now();
        if (now < next_t_) {
            py::gil_scoped_release release;
            std::this_thread::sleep_for(next_t_ - now);
        }
        if (stop_requested_) {
            return stop_frame();
        }
        next_t_ += std::chrono::duration_cast<std::chrono::steady_clock::duration>(
            std::chrono::duration<double>(frame_period_));

        seq_ += 1;
        return Frame(
            width_,
            height_,
            FOURCC_RGB24,
            render(seq_),
            now_pts_100ns(),
            seq_,
            FLAG_PLACEHOLDER,
            {width_ * 3, 0},
            {width_ * height_ * 3, 0},
            py::dict());
    }

    void close() {
        stop_requested_ = true;
        opened_ = false;
    }

    void request_stop() {
        stop_requested_ = true;
    }

private:
    py::array_t<std::uint8_t> render(std::uint64_t seq) const {
        auto data = py::array_t<std::uint8_t>(static_cast<py::ssize_t>(width_) * height_ * 3);
        auto* out = data.mutable_data();

        if (pattern_ == "gradient") {
            render_gradient(out, seq);
            return data;
        }
        if (pattern_ == "checkerboard") {
            render_checkerboard(out, seq);
            return data;
        }
        if (pattern_ == "noise") {
            render_noise(out, seq);
            return data;
        }
        if (pattern_ == "solid") {
            render_solid(out, seq);
            return data;
        }
        if (pattern_ == "moving_box") {
            render_moving_box(out, seq);
            return data;
        }
        render_colorbar(out, seq);
        return data;
    }

    Frame stop_frame() const {
        auto data = py::array_t<std::uint8_t>(static_cast<py::ssize_t>(width_) * height_ * 3);
        std::memset(data.mutable_data(), 0, static_cast<std::size_t>(data.nbytes()));
        py::dict meta;
        meta["reason"] = "stop requested";
        return Frame(
            width_,
            height_,
            FOURCC_RGB24,
            std::move(data),
            now_pts_100ns(),
            seq_,
            FLAG_ERROR,
            {width_ * 3, 0},
            {width_ * height_ * 3, 0},
            std::move(meta));
    }

    void render_colorbar(std::uint8_t* out, std::uint64_t seq) const {
        static constexpr std::uint8_t colors[8][3] = {
            {192, 192, 192},
            {0, 192, 192},
            {192, 192, 0},
            {0, 192, 0},
            {192, 0, 192},
            {0, 0, 192},
            {192, 0, 0},
            {16, 16, 16},
        };
        const std::int32_t bars = 8;
        const std::int32_t bar_w = std::max<std::int32_t>(1, width_ / bars);
        for (std::int32_t y = 0; y < height_; ++y) {
            for (std::int32_t x = 0; x < width_; ++x) {
                const std::int32_t bar = std::min<std::int32_t>(bars - 1, x / bar_w);
                auto* px = pixel_at(out, x, y);
                px[0] = colors[bar][0];
                px[1] = colors[bar][1];
                px[2] = colors[bar][2];
            }
        }
        if (height_ > 0) {
            const std::int32_t scan_y = static_cast<std::int32_t>((seq * 4) % static_cast<std::uint64_t>(height_));
            for (std::int32_t x = 0; x < width_; ++x) {
                auto* px = pixel_at(out, x, scan_y);
                px[0] = 255;
                px[1] = 255;
                px[2] = 255;
            }
        }
    }

    void render_gradient(std::uint8_t* out, std::uint64_t seq) const {
        const float t = static_cast<float>(seq) * 0.02f;
        for (std::int32_t y = 0; y < height_; ++y) {
            for (std::int32_t x = 0; x < width_; ++x) {
                const float xf = static_cast<float>(x);
                auto* px = pixel_at(out, x, y);
                px[2] = static_cast<std::uint8_t>(std::fmod(xf + t * 50.0f, 256.0f));
                px[1] = static_cast<std::uint8_t>(std::fmod(xf * 0.5f + t * 30.0f, 256.0f));
                px[0] = static_cast<std::uint8_t>(std::fmod(255.0f - xf * 0.3f + t * 20.0f + 2560.0f, 256.0f));
            }
        }
    }

    void render_checkerboard(std::uint8_t* out, std::uint64_t seq) const {
        const std::int32_t size = 40;
        const std::int32_t offset = static_cast<std::int32_t>((seq * 2) % size);
        for (std::int32_t y = 0; y < height_; ++y) {
            const std::int32_t y_cell = y / size;
            for (std::int32_t x = 0; x < width_; ++x) {
                const std::int32_t x_cell = (x + offset) / size;
                const bool light = ((x_cell + y_cell) % 2) == 0;
                const std::uint8_t shade = light ? 200 : 30;
                auto* px = pixel_at(out, x, y);
                px[0] = shade;
                px[1] = shade;
                px[2] = shade;
            }
        }
    }

    void render_noise(std::uint8_t* out, std::uint64_t seq) const {
        std::uint64_t state = seq ^ 0x9E3779B97F4A7C15ull;
        const std::size_t total = static_cast<std::size_t>(width_) * height_ * 3;
        for (std::size_t i = 0; i < total; ++i) {
            state ^= state >> 12;
            state ^= state << 25;
            state ^= state >> 27;
            out[i] = static_cast<std::uint8_t>((state * 2685821657736338717ull) >> 56);
        }
    }

    void render_solid(std::uint8_t* out, std::uint64_t seq) const {
        for (std::int32_t y = 0; y < height_; ++y) {
            for (std::int32_t x = 0; x < width_; ++x) {
                auto* px = pixel_at(out, x, y);
                px[0] = 0;
                px[1] = 0;
                px[2] = 180;
            }
        }
        if ((seq / 15) % 2 != 0 || width_ <= 0 || height_ <= 0) {
            return;
        }
        const std::int32_t cx = width_ / 2;
        const std::int32_t cy = height_ / 2;
        fill_rect(out, cx - 2, cy - 20, cx + 2, cy + 20, 255, 255, 255);
        fill_rect(out, cx - 20, cy - 2, cx + 20, cy + 2, 255, 255, 255);
    }

    void render_moving_box(std::uint8_t* out, std::uint64_t seq) const {
        std::memset(out, 20, static_cast<std::size_t>(width_) * height_ * 3);
        const std::int32_t box_size = std::min<std::int32_t>(80, std::max<std::int32_t>(1, std::min(width_, height_)));
        const std::int32_t period = 120;
        const std::uint64_t t = seq % static_cast<std::uint64_t>(period);
        const double progress = static_cast<double>(t) / static_cast<double>(period);
        const std::int32_t x = static_cast<std::int32_t>(progress * std::max<std::int32_t>(0, width_ - box_size));
        const std::int32_t y = static_cast<std::int32_t>((1.0 - std::abs(2.0 * progress - 1.0)) * std::max<std::int32_t>(0, height_ - box_size));
        const std::uint8_t b = static_cast<std::uint8_t>((seq * 5) % 256);
        const std::uint8_t g = static_cast<std::uint8_t>((seq * 3) % 256);
        const std::uint8_t r = static_cast<std::uint8_t>((seq * 7) % 256);
        fill_rect(out, x, y, x + box_size, y + box_size, b, g, r);
        fill_rect(out, x, y, x + 1, y + box_size, 255, 255, 255);
        fill_rect(out, x + box_size - 1, y, x + box_size, y + box_size, 255, 255, 255);
        fill_rect(out, x, y, x + box_size, y + 1, 255, 255, 255);
        fill_rect(out, x, y + box_size - 1, x + box_size, y + box_size, 255, 255, 255);
    }

    std::uint8_t* pixel_at(std::uint8_t* out, std::int32_t x, std::int32_t y) const {
        return out + (static_cast<std::size_t>(y) * width_ + x) * 3;
    }

    void fill_rect(
        std::uint8_t* out,
        std::int32_t x0,
        std::int32_t y0,
        std::int32_t x1,
        std::int32_t y1,
        std::uint8_t b,
        std::uint8_t g,
        std::uint8_t r) const {
        const std::int32_t left = std::max<std::int32_t>(0, x0);
        const std::int32_t top = std::max<std::int32_t>(0, y0);
        const std::int32_t right = std::min<std::int32_t>(width_, x1);
        const std::int32_t bottom = std::min<std::int32_t>(height_, y1);
        for (std::int32_t y = top; y < bottom; ++y) {
            for (std::int32_t x = left; x < right; ++x) {
                auto* px = pixel_at(out, x, y);
                px[0] = b;
                px[1] = g;
                px[2] = r;
            }
        }
    }

    std::int32_t width_;
    std::int32_t height_;
    std::int32_t fps_;
    std::string pattern_;
    double frame_period_;
    std::chrono::steady_clock::time_point next_t_{};
    std::uint64_t seq_ = 0;
    bool stop_requested_ = false;
    bool opened_ = false;
};

void bind_test_pattern_provider(py::module_& m) {
    py::class_<NativeTestPatternProvider>(m, "NativeTestPatternProvider")
        .def(py::init<std::int32_t, std::int32_t, std::int32_t, const std::string&>(), py::arg("width"), py::arg("height"), py::arg("fps"), py::arg("pattern"))
        .def("open", &NativeTestPatternProvider::open)
        .def("read", &NativeTestPatternProvider::read)
        .def("request_stop", &NativeTestPatternProvider::request_stop)
        .def("close", &NativeTestPatternProvider::close);
}

}  // namespace akvc::core_native
