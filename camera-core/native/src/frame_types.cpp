#define NOMINMAX

#include "akvc/core_native/frame_types.h"

#include <algorithm>
#include <chrono>
#include <cstring>
#include <sstream>

#ifdef _WIN32
#include <windows.h>
#endif

namespace akvc::core_native {

std::string fourcc_name(std::uint32_t fourcc) {
    switch (fourcc) {
    case FOURCC_NV12:
        return "NV12";
    case FOURCC_YUY2:
        return "YUY2";
    case FOURCC_RGB24:
        return "RGB24";
    case FOURCC_MJPG:
        return "MJPG";
    default: {
        std::ostringstream oss;
        oss << "0x" << std::uppercase << std::hex;
        oss.width(8);
        oss.fill('0');
        oss << fourcc;
        return oss.str();
    }
    }
}

std::int64_t now_pts_100ns() {
#ifdef _WIN32
    FILETIME ft;
    ::GetSystemTimePreciseAsFileTime(&ft);
    ULARGE_INTEGER u;
    u.LowPart = ft.dwLowDateTime;
    u.HighPart = ft.dwHighDateTime;
    return static_cast<std::int64_t>(u.QuadPart);
#else
    using namespace std::chrono;
    return duration_cast<duration<std::int64_t, std::ratio<1, 10000000>>>(
               system_clock::now().time_since_epoch())
        .count();
#endif
}

std::uint8_t clamp_u8(int value) {
    return static_cast<std::uint8_t>(std::max(0, std::min(255, value)));
}

Frame::Frame(
    std::int32_t width,
    std::int32_t height,
    std::uint32_t fourcc,
    py::array_t<std::uint8_t, py::array::c_style | py::array::forcecast> data,
    std::int64_t pts_100ns,
    std::uint64_t seq,
    std::uint32_t flags,
    std::pair<std::int32_t, std::int32_t> stride,
    std::pair<std::int32_t, std::int32_t> plane_size,
    py::dict meta)
    : width(width),
      height(height),
      fourcc(fourcc),
      data(std::move(data)),
      pts_100ns(pts_100ns == 0 ? now_pts_100ns() : pts_100ns),
      seq(seq),
      flags(flags),
      stride(std::move(stride)),
      plane_size(std::move(plane_size)),
      meta(std::move(meta)) {}

Frame Frame::make_nv12(
    py::array y_plane,
    py::array uv_plane,
    py::object pts_100ns,
    std::uint64_t seq,
    std::uint32_t flags) {
    auto y = py::array_t<std::uint8_t, py::array::c_style | py::array::forcecast>(y_plane);
    auto uv = py::array_t<std::uint8_t, py::array::c_style | py::array::forcecast>(uv_plane);
    if (y.ndim() != 2 || uv.ndim() != 2) {
        throw py::value_error("NV12 planes must be 2-D");
    }
    const auto h = static_cast<std::int32_t>(y.shape(0));
    const auto w = static_cast<std::int32_t>(y.shape(1));
    auto out = py::array_t<std::uint8_t>(y.size() + uv.size());
    std::memcpy(out.mutable_data(), y.data(), static_cast<std::size_t>(y.nbytes()));
    std::memcpy(static_cast<std::uint8_t*>(out.mutable_data()) + y.nbytes(), uv.data(), static_cast<std::size_t>(uv.nbytes()));
    return Frame(
        w,
        h,
        FOURCC_NV12,
        out,
        pts_100ns.is_none() ? now_pts_100ns() : pts_100ns.cast<std::int64_t>(),
        seq,
        flags,
        {w, w},
        {static_cast<std::int32_t>(y.nbytes()), static_cast<std::int32_t>(uv.nbytes())},
        py::dict());
}

Frame Frame::from_bgr(
    py::array bgr,
    py::object pts_100ns,
    std::uint64_t seq,
    std::uint32_t flags) {
    auto arr = py::array_t<std::uint8_t, py::array::c_style | py::array::forcecast>(bgr);
    if (arr.ndim() != 3 || arr.shape(2) != 3) {
        throw py::value_error("BGR frame must be HxWx3");
    }
    const auto h = static_cast<std::int32_t>(arr.shape(0));
    const auto w = static_cast<std::int32_t>(arr.shape(1));
    auto out = py::array_t<std::uint8_t>(arr.size());
    std::memcpy(out.mutable_data(), arr.data(), static_cast<std::size_t>(arr.nbytes()));
    return Frame(
        w,
        h,
        FOURCC_RGB24,
        out,
        pts_100ns.is_none() ? now_pts_100ns() : pts_100ns.cast<std::int64_t>(),
        seq,
        flags,
        {w * 3, 0},
        {w * h * 3, 0},
        py::dict());
}

void bind_frame_types(py::module_& m) {
    py::class_<Frame>(m, "Frame")
        .def(
            py::init<std::int32_t, std::int32_t, std::uint32_t, py::array_t<std::uint8_t, py::array::c_style | py::array::forcecast>, std::int64_t, std::uint64_t, std::uint32_t, std::pair<std::int32_t, std::int32_t>, std::pair<std::int32_t, std::int32_t>, py::dict>(),
            py::arg("width"),
            py::arg("height"),
            py::arg("fourcc"),
            py::arg("data"),
            py::arg("pts_100ns") = 0,
            py::arg("seq") = 0,
            py::arg("flags") = FLAG_NONE,
            py::arg("stride") = std::pair<std::int32_t, std::int32_t>(0, 0),
            py::arg("plane_size") = std::pair<std::int32_t, std::int32_t>(0, 0),
            py::arg("meta") = py::dict())
        .def_readwrite("width", &Frame::width)
        .def_readwrite("height", &Frame::height)
        .def_readwrite("fourcc", &Frame::fourcc)
        .def_readwrite("data", &Frame::data)
        .def_readwrite("pts_100ns", &Frame::pts_100ns)
        .def_readwrite("seq", &Frame::seq)
        .def_readwrite("flags", &Frame::flags)
        .def_readwrite("stride", &Frame::stride)
        .def_readwrite("plane_size", &Frame::plane_size)
        .def_readwrite("meta", &Frame::meta)
        .def_static("now_pts_100ns", &now_pts_100ns)
        .def_static("make_nv12", &Frame::make_nv12, py::arg("y_plane"), py::arg("uv_plane"), py::arg("pts_100ns") = py::none(), py::arg("seq") = 0, py::arg("flags") = FLAG_NONE)
        .def_static("from_bgr", &Frame::from_bgr, py::arg("bgr"), py::arg("pts_100ns") = py::none(), py::arg("seq") = 0, py::arg("flags") = FLAG_NONE);

    m.attr("FOURCC_NV12") = py::int_(FOURCC_NV12);
    m.attr("FOURCC_YUY2") = py::int_(FOURCC_YUY2);
    m.attr("FOURCC_RGB24") = py::int_(FOURCC_RGB24);
    m.attr("FOURCC_MJPG") = py::int_(FOURCC_MJPG);
    m.attr("FLAG_NONE") = py::int_(FLAG_NONE);
    m.attr("FLAG_KEYFRAME") = py::int_(FLAG_KEYFRAME);
    m.attr("FLAG_DISCONTINUITY") = py::int_(FLAG_DISCONTINUITY);
    m.attr("FLAG_PLACEHOLDER") = py::int_(FLAG_PLACEHOLDER);
    m.attr("FLAG_STALE") = py::int_(FLAG_STALE);
    m.attr("FLAG_ERROR") = py::int_(FLAG_ERROR);
    m.def("fourcc_name", &fourcc_name);
}

}  // namespace akvc::core_native
