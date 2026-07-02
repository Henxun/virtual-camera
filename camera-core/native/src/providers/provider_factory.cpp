#define NOMINMAX

#include "akvc/core_native/bindings.h"
#include "akvc/core_native/frame_types.h"

#include <cstdint>
#include <string>
#include <utility>
#include <vector>

namespace akvc::core_native {

namespace {

constexpr std::int32_t DEFAULT_PROVIDER_WIDTH = 1280;
constexpr std::int32_t DEFAULT_PROVIDER_HEIGHT = 720;
constexpr std::int32_t DEFAULT_PROVIDER_FPS = 30;

std::string normalize_pattern_id(const std::string& pattern_id) {
    static const std::vector<std::string> supported = {
        "colorbar",
        "gradient",
        "checkerboard",
        "noise",
        "solid",
        "moving_box",
    };
    for (const auto& candidate : supported) {
        if (candidate == pattern_id) {
            return candidate;
        }
    }
    return "colorbar";
}

std::string pattern_name(const std::string& pattern_id) {
    if (pattern_id == "gradient") {
        return "Gradient";
    }
    if (pattern_id == "checkerboard") {
        return "Checkerboard";
    }
    if (pattern_id == "noise") {
        return "Noise";
    }
    if (pattern_id == "solid") {
        return "Solid Red";
    }
    if (pattern_id == "moving_box") {
        return "Moving Box";
    }
    return "Color Bars";
}

NativeFormatSpec rgb24_format(
    std::int32_t width = DEFAULT_PROVIDER_WIDTH,
    std::int32_t height = DEFAULT_PROVIDER_HEIGHT,
    std::int32_t fps = DEFAULT_PROVIDER_FPS
) {
    return NativeFormatSpec{
        static_cast<std::int32_t>(FOURCC_RGB24),
        width,
        height,
        fps,
        1,
    };
}

NativeProviderInfo make_usb_provider_info(
    std::int32_t device_index,
    std::int32_t width = DEFAULT_PROVIDER_WIDTH,
    std::int32_t height = DEFAULT_PROVIDER_HEIGHT,
    std::int32_t fps = DEFAULT_PROVIDER_FPS
) {
    return NativeProviderInfo{
        "usb:" + std::to_string(device_index),
        "USB Camera " + std::to_string(device_index),
        {rgb24_format(width, height, fps)},
    };
}

NativeProviderInfo make_test_provider_info(
    const std::string& pattern_id,
    std::int32_t width = DEFAULT_PROVIDER_WIDTH,
    std::int32_t height = DEFAULT_PROVIDER_HEIGHT,
    std::int32_t fps = DEFAULT_PROVIDER_FPS
) {
    const std::string normalized = normalize_pattern_id(pattern_id);
    return NativeProviderInfo{
        "test:" + normalized,
        pattern_name(normalized),
        {rgb24_format(width, height, fps)},
    };
}

std::vector<std::string> list_pattern_ids_impl() {
    return {
        "colorbar",
        "gradient",
        "checkerboard",
        "noise",
        "solid",
        "moving_box",
    };
}

}  // namespace

py::dict parse_source_id(const std::string& source_id) {
    py::dict out;
    if (source_id.rfind("usb:", 0) == 0) {
        std::int32_t device_index = 0;
        try {
            device_index = std::stoi(source_id.substr(4));
        } catch (...) {
            device_index = 0;
        }
        out["kind"] = py::str("usb");
        out["device_index"] = py::int_(device_index);
        out["pattern_id"] = py::none();
        return out;
    }

    std::string pattern_id = "colorbar";
    const auto pos = source_id.find(':');
    if (pos != std::string::npos && pos + 1 < source_id.size()) {
        pattern_id = source_id.substr(pos + 1);
    }
    out["kind"] = py::str("test");
    out["device_index"] = py::none();
    out["pattern_id"] = py::str(normalize_pattern_id(pattern_id));
    return out;
}

std::vector<std::string> list_pattern_ids() {
    return list_pattern_ids_impl();
}

NativeProviderInfo describe_source_id(
    const std::string& source_id,
    std::int32_t width = DEFAULT_PROVIDER_WIDTH,
    std::int32_t height = DEFAULT_PROVIDER_HEIGHT,
    std::int32_t fps = DEFAULT_PROVIDER_FPS
) {
    py::dict parsed = parse_source_id(source_id);
    const std::string kind = py::str(parsed["kind"]).cast<std::string>();
    if (kind == "usb") {
        return make_usb_provider_info(
            py::int_(parsed["device_index"]).cast<std::int32_t>(),
            width,
            height,
            fps
        );
    }
    std::string pattern_id = "colorbar";
    if (!parsed["pattern_id"].is_none()) {
        pattern_id = py::str(parsed["pattern_id"]).cast<std::string>();
    }
    return make_test_provider_info(pattern_id, width, height, fps);
}

std::vector<NativeProviderInfo> list_test_pattern_sources(
    std::int32_t width = DEFAULT_PROVIDER_WIDTH,
    std::int32_t height = DEFAULT_PROVIDER_HEIGHT,
    std::int32_t fps = DEFAULT_PROVIDER_FPS
) {
    std::vector<NativeProviderInfo> out;
    for (const auto& pattern_id : list_pattern_ids_impl()) {
        out.push_back(make_test_provider_info(pattern_id, width, height, fps));
    }
    return out;
}

std::vector<NativeProviderInfo> list_usb_sources(
    std::int32_t max_probe = 8,
    std::int32_t width = DEFAULT_PROVIDER_WIDTH,
    std::int32_t height = DEFAULT_PROVIDER_HEIGHT,
    std::int32_t fps = DEFAULT_PROVIDER_FPS
) {
    py::module_ native = py::module_::import("akvc._core_native");
    py::object prober = native.attr("NativeUsbDeviceProber")();
    py::list indices = prober.attr("list_indices")(max_probe);
    std::vector<NativeProviderInfo> out;
    for (py::handle index_obj : indices) {
        const auto device_index = index_obj.cast<std::int32_t>();
        out.push_back(make_usb_provider_info(device_index, width, height, fps));
    }
    return out;
}

void bind_provider_factory(py::module_& m) {
    py::class_<NativeFormatSpec>(m, "NativeFormatSpec")
        .def_readonly("fourcc", &NativeFormatSpec::fourcc)
        .def_readonly("width", &NativeFormatSpec::width)
        .def_readonly("height", &NativeFormatSpec::height)
        .def_readonly("fps_num", &NativeFormatSpec::fps_num)
        .def_readonly("fps_den", &NativeFormatSpec::fps_den);

    py::class_<NativeProviderInfo>(m, "NativeProviderInfo")
        .def_readonly("id", &NativeProviderInfo::id)
        .def_readonly("name", &NativeProviderInfo::name)
        .def_readonly("formats", &NativeProviderInfo::formats);

    m.def("parse_source_id", &parse_source_id, py::arg("source_id"));
    m.def("list_pattern_ids", &list_pattern_ids);
    m.def(
        "describe_source_id",
        &describe_source_id,
        py::arg("source_id"),
        py::arg("width") = DEFAULT_PROVIDER_WIDTH,
        py::arg("height") = DEFAULT_PROVIDER_HEIGHT,
        py::arg("fps") = DEFAULT_PROVIDER_FPS
    );
    m.def(
        "list_test_pattern_sources",
        &list_test_pattern_sources,
        py::arg("width") = DEFAULT_PROVIDER_WIDTH,
        py::arg("height") = DEFAULT_PROVIDER_HEIGHT,
        py::arg("fps") = DEFAULT_PROVIDER_FPS
    );
    m.def(
        "list_usb_sources",
        &list_usb_sources,
        py::arg("max_probe") = 8,
        py::arg("width") = DEFAULT_PROVIDER_WIDTH,
        py::arg("height") = DEFAULT_PROVIDER_HEIGHT,
        py::arg("fps") = DEFAULT_PROVIDER_FPS
    );
}

}  // namespace akvc::core_native
