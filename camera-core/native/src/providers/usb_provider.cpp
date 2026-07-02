#define NOMINMAX
#define WIN32_LEAN_AND_MEAN

#include "akvc/core_native/frame_types.h"

#ifdef _WIN32
#include <combaseapi.h>
#include <mfapi.h>
#include <mfidl.h>
#include <mfobjects.h>
#include <mfreadwrite.h>
#include <windows.h>
#include <wrl/client.h>
#endif

#include <chrono>
#include <cstring>
#include <memory>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <thread>
#include <vector>

namespace akvc::core_native {

namespace {

std::string hresult_message(const char* what, long hr) {
    std::ostringstream oss;
    oss << what << " failed: 0x" << std::hex << std::uppercase << static_cast<unsigned long>(hr);
    return oss.str();
}

class NativeFpsRegulator {
public:
    NativeFpsRegulator(double target_fps, double jitter_pct)
        : target_fps_(target_fps),
          period_(1.0 / target_fps),
          jitter_(jitter_pct / 100.0) {}

    void reconfigure(const py::dict& cfg) {
        if (cfg.contains("target_fps")) {
            target_fps_ = py::float_(cfg["target_fps"]);
            period_ = 1.0 / target_fps_;
        }
    }

    Frame process(const Frame& frame) {
        const auto now = std::chrono::steady_clock::now();
        if (!last_t_.has_value()) {
            last_t_ = now;
            return frame;
        }
        const double elapsed = std::chrono::duration<double>(now - *last_t_).count();
        const double target = period_ * (1.0 - jitter_);
        if (elapsed < target) {
            std::this_thread::sleep_for(std::chrono::duration<double>(target - elapsed));
        }
        last_t_ = std::chrono::steady_clock::now();
        return frame;
    }

private:
    double target_fps_;
    double period_;
    double jitter_;
    std::optional<std::chrono::steady_clock::time_point> last_t_;
};

#ifdef _WIN32

using Microsoft::WRL::ComPtr;

class ScopedMfContext {
public:
    ScopedMfContext() {
        const HRESULT co_hr = ::CoInitializeEx(nullptr, COINIT_MULTITHREADED);
        if (SUCCEEDED(co_hr)) {
            should_uninitialize_com_ = true;
        } else if (co_hr != RPC_E_CHANGED_MODE) {
            throw std::runtime_error(hresult_message("CoInitializeEx", co_hr));
        }

        const HRESULT mf_hr = ::MFStartup(MF_VERSION, MFSTARTUP_FULL);
        if (FAILED(mf_hr)) {
            if (should_uninitialize_com_) {
                ::CoUninitialize();
                should_uninitialize_com_ = false;
            }
            throw std::runtime_error(hresult_message("MFStartup", mf_hr));
        }
        should_shutdown_mf_ = true;
    }

    ~ScopedMfContext() {
        if (should_shutdown_mf_) {
            ::MFShutdown();
        }
        if (should_uninitialize_com_) {
            ::CoUninitialize();
        }
    }

    ScopedMfContext(const ScopedMfContext&) = delete;
    ScopedMfContext& operator=(const ScopedMfContext&) = delete;

private:
    bool should_uninitialize_com_ = false;
    bool should_shutdown_mf_ = false;
};

std::vector<ComPtr<IMFActivate>> enumerate_video_devices() {
    ComPtr<IMFAttributes> attrs;
    HRESULT hr = ::MFCreateAttributes(&attrs, 1);
    if (FAILED(hr)) {
        throw std::runtime_error(hresult_message("MFCreateAttributes", hr));
    }

    hr = attrs->SetGUID(MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE, MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_GUID);
    if (FAILED(hr)) {
        throw std::runtime_error(hresult_message("SetGUID(MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE)", hr));
    }

    IMFActivate** raw_devices = nullptr;
    UINT32 raw_count = 0;
    hr = ::MFEnumDeviceSources(attrs.Get(), &raw_devices, &raw_count);
    if (FAILED(hr)) {
        throw std::runtime_error(hresult_message("MFEnumDeviceSources", hr));
    }

    std::vector<ComPtr<IMFActivate>> devices;
    devices.reserve(raw_count);
    for (UINT32 i = 0; i < raw_count; ++i) {
        devices.emplace_back(raw_devices[i]);
        raw_devices[i] = nullptr;
    }

    if (raw_devices != nullptr) {
        for (UINT32 i = 0; i < raw_count; ++i) {
            if (raw_devices[i] != nullptr) {
                raw_devices[i]->Release();
            }
        }
        ::CoTaskMemFree(raw_devices);
    }
    return devices;
}

class NativeUsbCaptureSession {
public:
    NativeUsbCaptureSession(std::int32_t width, std::int32_t height, std::int32_t fps)
        : desired_width_(width),
          desired_height_(height),
          desired_fps_(fps) {}

    void open(std::int32_t device_index, const std::string&) {
        close();
        stop_requested_ = false;
        context_ = std::make_unique<ScopedMfContext>();

        auto devices = enumerate_video_devices();
        if (device_index < 0 || static_cast<std::size_t>(device_index) >= devices.size()) {
            std::ostringstream oss;
            oss << "Cannot open USB camera " << device_index << ": device index out of range";
            throw std::runtime_error(oss.str());
        }

        HRESULT hr = devices[static_cast<std::size_t>(device_index)]->ActivateObject(IID_PPV_ARGS(&source_));
        if (FAILED(hr)) {
            throw std::runtime_error(hresult_message("IMFActivate::ActivateObject", hr));
        }

        ComPtr<IMFAttributes> reader_attrs;
        hr = ::MFCreateAttributes(&reader_attrs, 2);
        if (FAILED(hr)) {
            throw std::runtime_error(hresult_message("MFCreateAttributes(reader)", hr));
        }
        reader_attrs->SetUINT32(MF_SOURCE_READER_ENABLE_VIDEO_PROCESSING, TRUE);
        reader_attrs->SetUINT32(MF_READWRITE_ENABLE_HARDWARE_TRANSFORMS, TRUE);

        hr = ::MFCreateSourceReaderFromMediaSource(source_.Get(), reader_attrs.Get(), &reader_);
        if (FAILED(hr)) {
            throw std::runtime_error(hresult_message("MFCreateSourceReaderFromMediaSource", hr));
        }

        hr = reader_->SetStreamSelection(static_cast<DWORD>(MF_SOURCE_READER_ALL_STREAMS), FALSE);
        if (FAILED(hr)) {
            throw std::runtime_error(hresult_message("SetStreamSelection(all)", hr));
        }
        hr = reader_->SetStreamSelection(MF_SOURCE_READER_FIRST_VIDEO_STREAM, TRUE);
        if (FAILED(hr)) {
            throw std::runtime_error(hresult_message("SetStreamSelection(video)", hr));
        }

        configure_output_type();
    }

    Frame read_frame() {
        if (!reader_) {
            return error_frame("not opened");
        }

        try {
            auto frame = read_once();
            if (frame.has_value()) {
                return *frame;
            }

            {
                py::gil_scoped_release release;
                std::this_thread::sleep_for(std::chrono::milliseconds(5));
            }

            frame = read_once();
            if (frame.has_value()) {
                return *frame;
            }
            return error_frame("read failed");
        } catch (const std::exception& exc) {
            return error_frame(exc.what());
        }
    }

    void close() {
        stop_requested_ = true;
        current_type_.Reset();
        reader_.Reset();
        if (source_) {
            source_->Shutdown();
            source_.Reset();
        }
        context_.reset();
        current_width_ = desired_width_;
        current_height_ = desired_height_;
        current_stride_ = desired_width_ * 4;
        current_subtype_ = GUID_NULL;
    }

    void request_stop() {
        stop_requested_ = true;
    }

private:
    void configure_output_type() {
        static const GUID preferred_subtypes[] = {
            MFVideoFormat_RGB32,
            MFVideoFormat_RGB24,
        };

        HRESULT last_hr = E_FAIL;
        for (const auto& subtype : preferred_subtypes) {
            ComPtr<IMFMediaType> media_type;
            HRESULT hr = ::MFCreateMediaType(&media_type);
            if (FAILED(hr)) {
                throw std::runtime_error(hresult_message("MFCreateMediaType", hr));
            }
            media_type->SetGUID(MF_MT_MAJOR_TYPE, MFMediaType_Video);
            media_type->SetGUID(MF_MT_SUBTYPE, subtype);
            ::MFSetAttributeSize(media_type.Get(), MF_MT_FRAME_SIZE, desired_width_, desired_height_);
            ::MFSetAttributeRatio(media_type.Get(), MF_MT_FRAME_RATE, desired_fps_, 1);
            media_type->SetUINT32(MF_MT_INTERLACE_MODE, MFVideoInterlace_Progressive);
            media_type->SetUINT32(MF_MT_ALL_SAMPLES_INDEPENDENT, TRUE);

            hr = reader_->SetCurrentMediaType(MF_SOURCE_READER_FIRST_VIDEO_STREAM, nullptr, media_type.Get());
            if (SUCCEEDED(hr)) {
                refresh_current_type();
                return;
            }
            last_hr = hr;
        }

        refresh_current_type();
        if (current_subtype_ != MFVideoFormat_RGB32 && current_subtype_ != MFVideoFormat_RGB24) {
            throw std::runtime_error(hresult_message("SetCurrentMediaType(RGB)", last_hr));
        }
    }

    void refresh_current_type() {
        HRESULT hr = reader_->GetCurrentMediaType(MF_SOURCE_READER_FIRST_VIDEO_STREAM, &current_type_);
        if (FAILED(hr)) {
            throw std::runtime_error(hresult_message("GetCurrentMediaType", hr));
        }

        hr = current_type_->GetGUID(MF_MT_SUBTYPE, &current_subtype_);
        if (FAILED(hr)) {
            throw std::runtime_error(hresult_message("GetGUID(MF_MT_SUBTYPE)", hr));
        }

        UINT32 width = 0;
        UINT32 height = 0;
        hr = ::MFGetAttributeSize(current_type_.Get(), MF_MT_FRAME_SIZE, &width, &height);
        if (FAILED(hr)) {
            throw std::runtime_error(hresult_message("MFGetAttributeSize(MF_MT_FRAME_SIZE)", hr));
        }
        current_width_ = static_cast<std::int32_t>(width);
        current_height_ = static_cast<std::int32_t>(height);

        UINT32 stride = 0;
        if (SUCCEEDED(current_type_->GetUINT32(MF_MT_DEFAULT_STRIDE, &stride))) {
            current_stride_ = static_cast<LONG>(stride);
        } else {
            current_stride_ = current_subtype_ == MFVideoFormat_RGB24 ? current_width_ * 3 : current_width_ * 4;
        }
    }

    std::optional<Frame> read_once() {
        if (stop_requested_) {
            return std::nullopt;
        }
        DWORD actual_stream_index = 0;
        DWORD stream_flags = 0;
        LONGLONG timestamp = 0;
        ComPtr<IMFSample> sample;

        const HRESULT hr = reader_->ReadSample(
            MF_SOURCE_READER_FIRST_VIDEO_STREAM,
            0,
            &actual_stream_index,
            &stream_flags,
            &timestamp,
            &sample);
        if (stop_requested_) {
            return std::nullopt;
        }
        if (FAILED(hr)) {
            throw std::runtime_error(hresult_message("IMFSourceReader::ReadSample", hr));
        }
        if (actual_stream_index != MF_SOURCE_READER_FIRST_VIDEO_STREAM) {
            return std::nullopt;
        }
        if (stream_flags & MF_SOURCE_READERF_CURRENTMEDIATYPECHANGED) {
            refresh_current_type();
        }
        if (stream_flags & (MF_SOURCE_READERF_ENDOFSTREAM | MF_SOURCE_READERF_ERROR)) {
            return std::nullopt;
        }
        if (!sample) {
            return std::nullopt;
        }

        return sample_to_frame(sample.Get(), timestamp);
    }

    Frame sample_to_frame(IMFSample* sample, LONGLONG timestamp) {
        ComPtr<IMFMediaBuffer> buffer;
        HRESULT hr = sample->ConvertToContiguousBuffer(&buffer);
        if (FAILED(hr)) {
            throw std::runtime_error(hresult_message("ConvertToContiguousBuffer", hr));
        }

        BYTE* src = nullptr;
        DWORD max_len = 0;
        DWORD current_len = 0;
        hr = buffer->Lock(&src, &max_len, &current_len);
        if (FAILED(hr)) {
            throw std::runtime_error(hresult_message("IMFMediaBuffer::Lock", hr));
        }

        auto out = py::array_t<std::uint8_t>(static_cast<py::ssize_t>(current_width_) * current_height_ * 3);
        auto* dst = out.mutable_data();
        const LONG stride = current_stride_ > 0 ? current_stride_ : static_cast<LONG>(current_len / std::max(1, current_height_));

        if (current_subtype_ == MFVideoFormat_RGB32) {
            for (std::int32_t row = 0; row < current_height_; ++row) {
                const BYTE* src_row = src + static_cast<std::size_t>(row) * stride;
                auto* dst_row = dst + static_cast<std::size_t>(row) * current_width_ * 3;
                for (std::int32_t col = 0; col < current_width_; ++col) {
                    dst_row[col * 3 + 0] = src_row[col * 4 + 0];
                    dst_row[col * 3 + 1] = src_row[col * 4 + 1];
                    dst_row[col * 3 + 2] = src_row[col * 4 + 2];
                }
            }
        } else if (current_subtype_ == MFVideoFormat_RGB24) {
            for (std::int32_t row = 0; row < current_height_; ++row) {
                const BYTE* src_row = src + static_cast<std::size_t>(row) * stride;
                auto* dst_row = dst + static_cast<std::size_t>(row) * current_width_ * 3;
                std::memcpy(dst_row, src_row, static_cast<std::size_t>(current_width_) * 3);
            }
        } else {
            buffer->Unlock();
            throw std::runtime_error("unsupported capture subtype");
        }

        buffer->Unlock();
        Frame frame(
            current_width_,
            current_height_,
            FOURCC_RGB24,
            out,
            timestamp > 0 ? timestamp : now_pts_100ns(),
            ++seq_,
            FLAG_NONE,
            {current_width_ * 3, 0},
            {current_width_ * current_height_ * 3, 0},
            py::dict());
        return frame;
    }

    Frame error_frame(const std::string& reason) const {
        const auto width = current_width_ > 0 ? current_width_ : desired_width_;
        const auto height = current_height_ > 0 ? current_height_ : desired_height_;
        auto data = py::array_t<std::uint8_t>(static_cast<py::ssize_t>(width) * height * 3);
        std::memset(data.mutable_data(), 0, static_cast<std::size_t>(data.nbytes()));
        py::dict meta;
        meta["reason"] = reason;
        return Frame(
            width,
            height,
            FOURCC_RGB24,
            std::move(data),
            now_pts_100ns(),
            seq_,
            FLAG_ERROR,
            {width * 3, 0},
            {width * height * 3, 0},
            std::move(meta));
    }

    std::int32_t desired_width_;
    std::int32_t desired_height_;
    std::int32_t desired_fps_;
    bool stop_requested_ = false;
    std::int32_t current_width_ = 0;
    std::int32_t current_height_ = 0;
    LONG current_stride_ = 0;
    GUID current_subtype_ = GUID_NULL;
    std::uint64_t seq_ = 0;
    std::unique_ptr<ScopedMfContext> context_;
    ComPtr<IMFMediaSource> source_;
    ComPtr<IMFSourceReader> reader_;
    ComPtr<IMFMediaType> current_type_;
};

#else

class NativeUsbCaptureSession {
public:
    NativeUsbCaptureSession(std::int32_t, std::int32_t, std::int32_t) {}

    void open(std::int32_t, const std::string&) {
        throw std::runtime_error("native USB capture is only supported on Windows");
    }

    Frame read_frame() {
        throw std::runtime_error("native USB capture is only supported on Windows");
    }

    void close() {}
};

#endif

class NativeUsbCaptureOpener {
public:
    NativeUsbCaptureOpener(std::int32_t width, std::int32_t height, std::int32_t fps)
        : width_(width),
          height_(height),
          fps_(fps) {}

    std::shared_ptr<NativeUsbCaptureSession> open(
        std::int32_t device_index,
        const std::string& backend,
        const py::object& = py::none(),
        const py::object& = py::none()) const {
        auto capture = std::make_shared<NativeUsbCaptureSession>(width_, height_, fps_);
        try {
            capture->open(device_index, backend);
        } catch (const std::exception& exc) {
            std::ostringstream oss;
            oss << "Cannot open USB camera " << device_index << ": " << exc.what();
            throw std::runtime_error(oss.str());
        }
        return capture;
    }

private:
    std::int32_t width_;
    std::int32_t height_;
    std::int32_t fps_;
};

class NativeUsbDeviceProber {
public:
    py::list list_indices(
        std::int32_t max_probe,
        const py::object& = py::none(),
        const py::object& = py::none()) const {
        py::list out;
        if (max_probe <= 0) {
            return out;
        }
#ifdef _WIN32
        ScopedMfContext context;
        const auto devices = enumerate_video_devices();
        const auto limit = std::min<std::size_t>(static_cast<std::size_t>(max_probe), devices.size());
        for (std::size_t i = 0; i < limit; ++i) {
            out.append(static_cast<std::int32_t>(i));
        }
#endif
        return out;
    }
};

class NativeUsbFrameReader {
public:
    NativeUsbFrameReader(std::int32_t width, std::int32_t height)
        : width_(width),
          height_(height) {}

    void clear_stop() {
        stop_requested_ = false;
    }

    void request_stop() {
        stop_requested_ = true;
    }

    Frame read(const py::object& capture) {
        if (capture.is_none()) {
            return error_frame("not opened");
        }
        if (stop_requested_) {
            return error_frame("stop requested");
        }

        try {
            auto native_capture = capture.cast<std::shared_ptr<NativeUsbCaptureSession>>();
            py::gil_scoped_release release;
            return native_capture->read_frame();
        } catch (const py::cast_error&) {
        }

        auto frame = read_legacy_once(capture);
        if (frame.has_value()) {
            return *frame;
        }
        if (stop_requested_) {
            return error_frame("stop requested");
        }

        {
            py::gil_scoped_release release;
            std::this_thread::sleep_for(std::chrono::milliseconds(5));
        }
        if (stop_requested_) {
            return error_frame("stop requested");
        }

        frame = read_legacy_once(capture);
        if (frame.has_value()) {
            return *frame;
        }
        return error_frame("read failed");
    }

private:
    std::optional<Frame> read_legacy_once(const py::object& capture) {
        py::tuple result = capture.attr("read")().cast<py::tuple>();
        if (result.size() != 2) {
            throw py::value_error("capture.read() must return (ok, frame)");
        }
        if (!result[0].cast<bool>()) {
            return std::nullopt;
        }
        py::object bgr = result[1];
        if (bgr.is_none()) {
            return std::nullopt;
        }
        seq_ += 1;
        return Frame::from_bgr(bgr, py::none(), seq_, FLAG_NONE);
    }

    Frame error_frame(const char* reason) const {
        auto data = py::array_t<std::uint8_t>(static_cast<py::ssize_t>(width_) * height_ * 3);
        std::memset(data.mutable_data(), 0, static_cast<std::size_t>(data.nbytes()));
        py::dict meta;
        meta["reason"] = reason;
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

    std::int32_t width_;
    std::int32_t height_;
    std::uint64_t seq_ = 0;
    bool stop_requested_ = false;
};

}  // namespace

void bind_usb_provider(py::module_& m) {
    py::class_<NativeFpsRegulator>(m, "NativeFpsRegulator")
        .def(py::init<double, double>(), py::arg("target_fps"), py::arg("jitter_pct") = 10.0)
        .def("reconfigure", &NativeFpsRegulator::reconfigure)
        .def("process", &NativeFpsRegulator::process);

    py::class_<NativeUsbCaptureSession, std::shared_ptr<NativeUsbCaptureSession>>(m, "NativeUsbCaptureSession")
        .def("read", &NativeUsbCaptureSession::read_frame)
        .def("request_stop", &NativeUsbCaptureSession::request_stop)
        .def("close", &NativeUsbCaptureSession::close);

    py::class_<NativeUsbCaptureOpener>(m, "NativeUsbCaptureOpener")
        .def(py::init<std::int32_t, std::int32_t, std::int32_t>(), py::arg("width"), py::arg("height"), py::arg("fps"))
        .def("open", &NativeUsbCaptureOpener::open, py::arg("device_index"), py::arg("backend"), py::arg("cv2_module") = py::none(), py::arg("capture_factory") = py::none());

    py::class_<NativeUsbDeviceProber>(m, "NativeUsbDeviceProber")
        .def(py::init<>())
        .def("list_indices", &NativeUsbDeviceProber::list_indices, py::arg("max_probe"), py::arg("cv2_module") = py::none(), py::arg("capture_factory") = py::none());

    py::class_<NativeUsbFrameReader>(m, "NativeUsbFrameReader")
        .def(py::init<std::int32_t, std::int32_t>(), py::arg("width"), py::arg("height"))
        .def("clear_stop", &NativeUsbFrameReader::clear_stop)
        .def("request_stop", &NativeUsbFrameReader::request_stop)
        .def("read", &NativeUsbFrameReader::read, py::arg("capture"));
}

}  // namespace akvc::core_native
