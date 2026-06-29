#include "akvc/core_native/frame_types.h"

#include <algorithm>
#include <cmath>
#include <vector>

namespace akvc::core_native {

Frame resize_rgb24_frame(const Frame& frame, std::int32_t target_w, std::int32_t target_h) {
    if (frame.fourcc != FOURCC_RGB24 || frame.width == target_w && frame.height == target_h) {
        return frame;
    }
    if (target_w <= 0 || target_h <= 0) {
        throw py::value_error("target dimensions must be positive");
    }

    auto src = frame.data.unchecked<1>();
    auto out = py::array_t<std::uint8_t>(static_cast<py::ssize_t>(target_w) * target_h * 3);
    auto dst = out.mutable_unchecked<1>();

    const float scale_x = static_cast<float>(frame.width) / static_cast<float>(target_w);
    const float scale_y = static_cast<float>(frame.height) / static_cast<float>(target_h);
    const bool downscale = target_w * target_h < frame.width * frame.height;

    for (int y = 0; y < target_h; ++y) {
        for (int x = 0; x < target_w; ++x) {
            for (int c = 0; c < 3; ++c) {
                int value = 0;
                if (downscale) {
                    const int src_x0 = std::min(frame.width - 1, static_cast<int>(std::floor(x * scale_x)));
                    const int src_x1 = std::min(frame.width, std::max(src_x0 + 1, static_cast<int>(std::ceil((x + 1) * scale_x))));
                    const int src_y0 = std::min(frame.height - 1, static_cast<int>(std::floor(y * scale_y)));
                    const int src_y1 = std::min(frame.height, std::max(src_y0 + 1, static_cast<int>(std::ceil((y + 1) * scale_y))));
                    int sum = 0;
                    int count = 0;
                    for (int sy = src_y0; sy < src_y1; ++sy) {
                        for (int sx = src_x0; sx < src_x1; ++sx) {
                            sum += src((sy * frame.width + sx) * 3 + c);
                            ++count;
                        }
                    }
                    value = count > 0 ? sum / count : 0;
                } else {
                    const float src_fx = (static_cast<float>(x) + 0.5F) * scale_x - 0.5F;
                    const float src_fy = (static_cast<float>(y) + 0.5F) * scale_y - 0.5F;
                    const int x0 = std::clamp(static_cast<int>(std::floor(src_fx)), 0, frame.width - 1);
                    const int y0 = std::clamp(static_cast<int>(std::floor(src_fy)), 0, frame.height - 1);
                    const int x1 = std::clamp(x0 + 1, 0, frame.width - 1);
                    const int y1 = std::clamp(y0 + 1, 0, frame.height - 1);
                    const float wx = src_fx - std::floor(src_fx);
                    const float wy = src_fy - std::floor(src_fy);
                    const float p00 = static_cast<float>(src((y0 * frame.width + x0) * 3 + c));
                    const float p01 = static_cast<float>(src((y0 * frame.width + x1) * 3 + c));
                    const float p10 = static_cast<float>(src((y1 * frame.width + x0) * 3 + c));
                    const float p11 = static_cast<float>(src((y1 * frame.width + x1) * 3 + c));
                    const float top = p00 + (p01 - p00) * wx;
                    const float bottom = p10 + (p11 - p10) * wx;
                    value = static_cast<int>(std::lround(top + (bottom - top) * wy));
                }
                dst((y * target_w + x) * 3 + c) = clamp_u8(value);
            }
        }
    }

    return Frame(
        target_w,
        target_h,
        FOURCC_RGB24,
        out,
        frame.pts_100ns,
        frame.seq,
        frame.flags,
        {target_w * 3, 0},
        {target_w * target_h * 3, 0},
        py::dict(frame.meta));
}

Frame rgb24_to_nv12_frame(const Frame& frame) {
    if (frame.fourcc == FOURCC_NV12) {
        return frame;
    }
    if (frame.fourcc != FOURCC_RGB24) {
        return frame;
    }

    const int w = frame.width;
    const int h = frame.height;
    auto src = frame.data.unchecked<1>();

    py::array_t<std::uint8_t> y_plane({h, w});
    py::array_t<std::uint8_t> uv_plane({h / 2, w});
    auto y = y_plane.mutable_unchecked<2>();
    auto uv = uv_plane.mutable_unchecked<2>();

    std::vector<std::uint8_t> cb(static_cast<std::size_t>(w) * h);
    std::vector<std::uint8_t> cr(static_cast<std::size_t>(w) * h);

    for (int row = 0; row < h; ++row) {
        for (int col = 0; col < w; ++col) {
            const auto idx = (row * w + col) * 3;
            const int b = src(idx + 0);
            const int g = src(idx + 1);
            const int r = src(idx + 2);

            const int yv = ((66 * r + 129 * g + 25 * b + 128) >> 8) + 16;
            const int uvv = ((-38 * r - 74 * g + 112 * b + 128) >> 8) + 128;
            const int vvv = ((112 * r - 94 * g - 18 * b + 128) >> 8) + 128;
            y(row, col) = clamp_u8(yv);
            cb[static_cast<std::size_t>(row) * w + col] = clamp_u8(uvv);
            cr[static_cast<std::size_t>(row) * w + col] = clamp_u8(vvv);
        }
    }

    for (int row = 0; row < h / 2; ++row) {
        for (int col = 0; col < w / 2; ++col) {
            const int r0 = row * 2;
            const int c0 = col * 2;
            const std::size_t i00 = static_cast<std::size_t>(r0) * w + c0;
            const std::size_t i01 = i00 + 1;
            const std::size_t i10 = static_cast<std::size_t>(r0 + 1) * w + c0;
            const std::size_t i11 = i10 + 1;
            uv(row, col * 2) = static_cast<std::uint8_t>((cb[i00] + cb[i01] + cb[i10] + cb[i11]) / 4);
            uv(row, col * 2 + 1) = static_cast<std::uint8_t>((cr[i00] + cr[i01] + cr[i10] + cr[i11]) / 4);
        }
    }

    return Frame::make_nv12(y_plane, uv_plane, py::int_(frame.pts_100ns), frame.seq, frame.flags);
}

Frame process_pipeline(py::iterable stages, const Frame& frame, py::object logger) {
    Frame current = frame;
    for (auto item : stages) {
        py::object stage = py::reinterpret_borrow<py::object>(item);
        py::object stage_name = py::str("<unknown>");
        try {
            stage_name = stage.attr("name");
        } catch (const py::error_already_set&) {
        }
        try {
            current = stage.attr("process")(current).cast<Frame>();
        } catch (const py::error_already_set& err) {
            if (!logger.is_none()) {
                logger.attr("error")(
                    py::str("pipeline stage {} failed; passing frame through: {}")
                        .format(stage_name, err.what()));
            }
        }
    }
    return current;
}

void bind_pipeline_ops(py::module_& m) {
    m.def("resize_rgb24_frame", &resize_rgb24_frame, py::arg("frame"), py::arg("target_w"), py::arg("target_h"));
    m.def("rgb24_to_nv12_frame", &rgb24_to_nv12_frame, py::arg("frame"));
    m.def("process_pipeline", &process_pipeline, py::arg("stages"), py::arg("frame"), py::arg("logger") = py::none());
}

}  // namespace akvc::core_native
