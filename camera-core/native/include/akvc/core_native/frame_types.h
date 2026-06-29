#pragma once

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <cstdint>
#include <string>
#include <utility>

namespace py = pybind11;

namespace akvc::core_native {

constexpr std::uint32_t FOURCC_NV12 = 0x3231564E;
constexpr std::uint32_t FOURCC_YUY2 = 0x32595559;
constexpr std::uint32_t FOURCC_RGB24 = 0x20424752;
constexpr std::uint32_t FOURCC_MJPG = 0x47504A4D;

constexpr std::uint32_t FLAG_NONE = 0;
constexpr std::uint32_t FLAG_KEYFRAME = 1;
constexpr std::uint32_t FLAG_DISCONTINUITY = 2;
constexpr std::uint32_t FLAG_PLACEHOLDER = 4;
constexpr std::uint32_t FLAG_STALE = 8;
constexpr std::uint32_t FLAG_ERROR = 16;

std::string fourcc_name(std::uint32_t fourcc);
std::int64_t now_pts_100ns();
std::uint8_t clamp_u8(int value);

class Frame {
public:
    Frame(
        std::int32_t width,
        std::int32_t height,
        std::uint32_t fourcc,
        py::array_t<std::uint8_t, py::array::c_style | py::array::forcecast> data,
        std::int64_t pts_100ns = 0,
        std::uint64_t seq = 0,
        std::uint32_t flags = FLAG_NONE,
        std::pair<std::int32_t, std::int32_t> stride = {0, 0},
        std::pair<std::int32_t, std::int32_t> plane_size = {0, 0},
        py::dict meta = py::dict());

    static Frame make_nv12(
        py::array y_plane,
        py::array uv_plane,
        py::object pts_100ns = py::none(),
        std::uint64_t seq = 0,
        std::uint32_t flags = FLAG_NONE);

    static Frame from_bgr(
        py::array bgr,
        py::object pts_100ns = py::none(),
        std::uint64_t seq = 0,
        std::uint32_t flags = FLAG_NONE);

    std::int32_t width;
    std::int32_t height;
    std::uint32_t fourcc;
    py::array_t<std::uint8_t, py::array::c_style | py::array::forcecast> data;
    std::int64_t pts_100ns;
    std::uint64_t seq;
    std::uint32_t flags;
    std::pair<std::int32_t, std::int32_t> stride;
    std::pair<std::int32_t, std::int32_t> plane_size;
    py::dict meta;
};

void bind_frame_types(py::module_& m);

}  // namespace akvc::core_native
