#define NOMINMAX

#include "akvc/core_native/frame_types.h"

#include <cerrno>
#include <cstdint>
#include <cstring>
#include <mutex>
#include <stdexcept>
#include <string>

#ifndef _WIN32
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
#endif

#include "akvc_protocol.h"

namespace akvc::core_native {

namespace {

#ifndef _WIN32
constexpr const char* SHM_NAME = AKVC_POSIX_SHM_NAME;
constexpr int O_RDWR_FLAGS = O_RDWR;
constexpr int O_CREATE_EXCL_FLAGS = O_RDWR | O_CREAT | O_EXCL;
#endif

std::string errno_message(const char* op, int err) {
    return std::string(op) + " failed (errno=" + std::to_string(err) + ")";
}

}  // namespace

class NativeMacOsShmSink {
public:
    NativeMacOsShmSink() = default;

    void open() {
#ifdef _WIN32
        throw std::runtime_error("MacOsShmSink can only run on macOS");
#else
        if (opened_) {
            return;
        }

        int fd = ::shm_open(SHM_NAME, O_RDWR_FLAGS, 0666);
        created_by_us_ = false;
        if (fd < 0) {
            fd = ::shm_open(SHM_NAME, O_CREATE_EXCL_FLAGS, 0666);
            if (fd < 0) {
                throw py::value_error(errno_message("shm_open(create)", errno));
            }
            created_by_us_ = true;
            if (::ftruncate(fd, static_cast<off_t>(AKVC_DEFAULT_REGION_SIZE)) != 0) {
                const int err = errno;
                ::close(fd);
                throw py::value_error(errno_message("ftruncate", err));
            }
        }
        fd_ = fd;

        void* addr = ::mmap(nullptr, AKVC_DEFAULT_REGION_SIZE, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
        if (addr == MAP_FAILED || addr == nullptr) {
            const int err = errno;
            ::close(fd_);
            fd_ = -1;
            throw py::value_error(errno_message("mmap", err));
        }
        base_ = static_cast<std::uint8_t*>(addr);

        auto* ctrl = ctrl_block();
        if (ctrl->magic != AKVC_MAGIC) {
            std::memset(base_, 0, AKVC_DEFAULT_REGION_SIZE);
            ctrl->magic = AKVC_MAGIC;
            ctrl->schema_version = AKVC_SCHEMA_VERSION;
            ctrl->slot_count = AKVC_RING_SLOTS;
            ctrl->slot_size = AKVC_DEFAULT_SLOT_SIZE;
            ctrl->producer_seq = 0;
            ctrl->writer_pid = static_cast<std::uint32_t>(::getpid());
            ctrl->consumer_count = 0;
            ctrl->created_pts_100ns = now_realtime_100ns();
            ctrl->producer_heartbeat = 0;
            ctrl->helper_pid = 0;
            state_seq_ = 0;
        } else {
            if (ctrl->schema_version != AKVC_SCHEMA_VERSION ||
                ctrl->slot_count != AKVC_RING_SLOTS ||
                ctrl->slot_size != AKVC_DEFAULT_SLOT_SIZE) {
                close();
                throw py::value_error("shared region schema mismatch");
            }
            state_seq_ = ctrl->producer_seq;
        }

        opened_ = true;
#endif
    }

    void close() {
#ifndef _WIN32
        if (base_ != nullptr) {
            ::munmap(base_, AKVC_DEFAULT_REGION_SIZE);
            base_ = nullptr;
        }
        if (fd_ >= 0) {
            ::close(fd_);
            fd_ = -1;
        }
#endif
        opened_ = false;
    }

    int consumer_count() const {
#ifdef _WIN32
        return 0;
#else
        if (!opened_) {
            return 0;
        }
        return static_cast<int>(ctrl_block()->consumer_count);
#endif
    }

    void publish(const Frame& frame) {
#ifdef _WIN32
        (void)frame;
        throw std::runtime_error("MacOsShmSink can only run on macOS");
#else
        ensure_open();
        if (frame.fourcc != FOURCC_NV12) {
            throw py::value_error("only NV12 supported");
        }

        const std::uint32_t plane_size_y = frame.plane_size.first ? static_cast<std::uint32_t>(frame.plane_size.first) : static_cast<std::uint32_t>(frame.width * frame.height);
        const std::uint32_t plane_size_uv = frame.plane_size.second ? static_cast<std::uint32_t>(frame.plane_size.second) : static_cast<std::uint32_t>(frame.width * frame.height / 2);
        const std::uint32_t total = static_cast<std::uint32_t>(sizeof(akvc_frame_header_t)) + plane_size_y + plane_size_uv;
        if (total > AKVC_DEFAULT_SLOT_SIZE) {
            throw py::value_error("frame too large for slot");
        }

        std::lock_guard<std::mutex> guard(lock_);
        state_seq_ += 1;
        const std::uint64_t seq = state_seq_;
        const std::uint32_t slot_index = static_cast<std::uint32_t>((seq - 1) % AKVC_RING_SLOTS);
        auto* slot = slot_ptr(slot_index);
        auto* hdr = reinterpret_cast<akvc_frame_header_t*>(slot);
        const std::uint32_t plane_off0 = static_cast<std::uint32_t>(sizeof(akvc_frame_header_t));
        const std::uint32_t plane_off1 = plane_off0 + plane_size_y;

        std::memset(hdr, 0, sizeof(*hdr));
        hdr->magic = AKVC_MAGIC;
        hdr->schema_version = AKVC_SCHEMA_VERSION;
        hdr->fourcc = frame.fourcc;
        hdr->width = static_cast<std::uint32_t>(frame.width);
        hdr->height = static_cast<std::uint32_t>(frame.height);
        hdr->stride[0] = frame.stride.first ? static_cast<std::uint32_t>(frame.stride.first) : static_cast<std::uint32_t>(frame.width);
        hdr->stride[1] = frame.stride.second ? static_cast<std::uint32_t>(frame.stride.second) : static_cast<std::uint32_t>(frame.width);
        hdr->plane_offset[0] = plane_off0;
        hdr->plane_offset[1] = plane_off1;
        hdr->plane_size[0] = plane_size_y;
        hdr->plane_size[1] = plane_size_uv;
        hdr->flags = frame.flags;
        hdr->pts_100ns = static_cast<std::uint64_t>(frame.pts_100ns);
        hdr->seq_head = seq;
        hdr->seq_tail = 0;

        auto data = frame.data.unchecked<1>();
        auto* payload = slot + plane_off0;
        std::memcpy(payload, reinterpret_cast<const std::uint8_t*>(data.data(0)), plane_size_y);
        std::memcpy(payload + plane_size_y, reinterpret_cast<const std::uint8_t*>(data.data(0)) + plane_size_y, plane_size_uv);

        hdr->seq_tail = seq;
        auto* ctrl = ctrl_block();
        ctrl->producer_seq = seq;
        ctrl->writer_pid = static_cast<std::uint32_t>(::getpid());
        ctrl->producer_heartbeat = now_realtime_100ns();
#endif
    }

private:
#ifndef _WIN32
    akvc_ring_control_t* ctrl_block() const {
        return reinterpret_cast<akvc_ring_control_t*>(base_);
    }

    std::uint8_t* slot_ptr(std::uint32_t slot_index) const {
        return base_ + sizeof(akvc_ring_control_t) + static_cast<std::size_t>(slot_index) * AKVC_DEFAULT_SLOT_SIZE;
    }

    static std::uint64_t now_realtime_100ns() {
        struct timespec ts{};
        if (::clock_gettime(CLOCK_REALTIME, &ts) != 0) {
            throw py::value_error("clock_gettime failed");
        }
        return static_cast<std::uint64_t>(ts.tv_sec) * 10000000ULL + static_cast<std::uint64_t>(ts.tv_nsec) / 100ULL;
    }
#endif

    void ensure_open() const {
        if (!opened_) {
            throw std::runtime_error("sink not opened");
        }
    }

    int fd_ = -1;
    std::uint8_t* base_ = nullptr;
    std::mutex lock_;
    std::uint64_t state_seq_ = 0;
    bool opened_ = false;
    bool created_by_us_ = false;
};

void bind_macos_shm_sink(py::module_& m) {
    py::class_<NativeMacOsShmSink>(m, "NativeMacOsShmSink")
        .def(py::init<>())
        .def("open", &NativeMacOsShmSink::open)
        .def("close", &NativeMacOsShmSink::close)
        .def("publish", &NativeMacOsShmSink::publish)
        .def_property_readonly("consumer_count", &NativeMacOsShmSink::consumer_count);
}

}  // namespace akvc::core_native
