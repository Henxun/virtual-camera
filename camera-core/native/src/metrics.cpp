#include "akvc/core_native/bindings.h"

#include <chrono>
#include <cmath>
#include <cstdint>
#include <deque>
#include <mutex>
#include <string>

namespace akvc::core_native {
namespace {

using Clock = std::chrono::steady_clock;

class NativeCounter {
public:
    NativeCounter(std::string name, std::int64_t value = 0)
        : name_(std::move(name)), value_(value) {}

    const std::string& name() const { return name_; }
    std::int64_t value() const { return value_; }
    void set_value(std::int64_t value) { value_ = value; }
    void inc(std::int64_t n = 1) { value_ += n; }

private:
    std::string name_;
    std::int64_t value_;
};

class NativeGauge {
public:
    NativeGauge(std::string name, double value = 0.0)
        : name_(std::move(name)), value_(value) {}

    const std::string& name() const { return name_; }
    double value() const { return value_; }
    void set_value(double value) { value_ = value; }
    void set(double value) { value_ = value; }

private:
    std::string name_;
    double value_;
};

class NativeRateMeter {
public:
    NativeRateMeter(std::string name, double window_s = 1.0)
        : name_(std::move(name)), window_s_(window_s <= 0.0 ? 1.0 : window_s) {}

    const std::string& name() const { return name_; }
    double window_s() const { return window_s_; }
    void set_window_s(double window_s) { window_s_ = window_s <= 0.0 ? 1.0 : window_s; }

    void tick() {
        const auto now = Clock::now();
        std::lock_guard<std::mutex> lock(lock_);
        events_.push_back(now);
        if (events_.size() > max_events_) {
            events_.pop_front();
        }
        trim_locked(now);
    }

    double rate() {
        std::lock_guard<std::mutex> lock(lock_);
        if (events_.empty()) {
            return 0.0;
        }
        trim_locked(Clock::now());
        return static_cast<double>(events_.size()) / window_s_;
    }

private:
    void trim_locked(Clock::time_point now) {
        const auto window = std::chrono::duration<double>(window_s_);
        while (!events_.empty() && (now - events_.front()) > window) {
            events_.pop_front();
        }
    }

    std::string name_;
    double window_s_;
    std::deque<Clock::time_point> events_;
    std::mutex lock_;
    static constexpr std::size_t max_events_ = 1024;
};

class NativeMetrics {
public:
    NativeMetrics()
        : fps_("akvc.fps"),
          frames_published_("akvc.frames_published"),
          frames_dropped_("akvc.frames_dropped"),
          last_publish_latency_ms_("akvc.publish_latency_ms") {}

    NativeRateMeter& fps() { return fps_; }
    NativeCounter& frames_published() { return frames_published_; }
    NativeCounter& frames_dropped() { return frames_dropped_; }
    NativeGauge& last_publish_latency_ms() { return last_publish_latency_ms_; }

    py::dict snapshot() {
        py::dict result;
        result["fps"] = round_to(fps_.rate(), 2);
        result["frames_published"] = frames_published_.value();
        result["frames_dropped"] = frames_dropped_.value();
        result["last_publish_latency_ms"] = round_to(last_publish_latency_ms_.value(), 3);
        return result;
    }

private:
    static double round_to(double value, double digits) {
        const double factor = digits == 2.0 ? 100.0 : 1000.0;
        return std::round(value * factor) / factor;
    }

    NativeRateMeter fps_;
    NativeCounter frames_published_;
    NativeCounter frames_dropped_;
    NativeGauge last_publish_latency_ms_;
};

}  // namespace

void bind_metrics(py::module_& m) {
    py::class_<NativeCounter>(m, "NativeCounter")
        .def(py::init<std::string, std::int64_t>(), py::arg("name"), py::arg("value") = 0)
        .def_property_readonly("name", &NativeCounter::name)
        .def_property("value", &NativeCounter::value, &NativeCounter::set_value)
        .def("inc", &NativeCounter::inc, py::arg("n") = 1);

    py::class_<NativeGauge>(m, "NativeGauge")
        .def(py::init<std::string, double>(), py::arg("name"), py::arg("value") = 0.0)
        .def_property_readonly("name", &NativeGauge::name)
        .def_property("value", &NativeGauge::value, &NativeGauge::set_value)
        .def("set", &NativeGauge::set, py::arg("v"));

    py::class_<NativeRateMeter>(m, "NativeRateMeter")
        .def(py::init<std::string, double>(), py::arg("name"), py::arg("window_s") = 1.0)
        .def_property_readonly("name", &NativeRateMeter::name)
        .def_property("window_s", &NativeRateMeter::window_s, &NativeRateMeter::set_window_s)
        .def("tick", &NativeRateMeter::tick)
        .def("rate", &NativeRateMeter::rate);

    py::class_<NativeMetrics>(m, "NativeMetrics")
        .def(py::init<>())
        .def_property_readonly("fps", &NativeMetrics::fps, py::return_value_policy::reference_internal)
        .def_property_readonly("frames_published", &NativeMetrics::frames_published, py::return_value_policy::reference_internal)
        .def_property_readonly("frames_dropped", &NativeMetrics::frames_dropped, py::return_value_policy::reference_internal)
        .def_property_readonly("last_publish_latency_ms", &NativeMetrics::last_publish_latency_ms, py::return_value_policy::reference_internal)
        .def("snapshot", &NativeMetrics::snapshot);
}

}  // namespace akvc::core_native
