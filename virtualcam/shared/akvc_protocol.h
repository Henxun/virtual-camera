// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors
//
// AK Virtual Camera — Frame Bus protocol (Windows + macOS shared)
//
// This header defines the wire protocol of the shared-memory ring buffer
// (Windows: named file mapping; macOS: IOSurface metadata header).
// All multi-byte integers are little-endian.
//
// Layout of the shared region:
//
//   +----------------------+
//   | akvc_ring_control_t  |  (cacheline-aligned, 128 bytes)
//   +----------------------+
//   | slot[0]              |
//   |  akvc_frame_header_t |  + payload
//   +----------------------+
//   | slot[1] ...          |
//   +----------------------+
//
// Tear protection: every slot has a leading and trailing copy of `seq`.
// Readers must compare them; if they differ, the slot is being written
// and must be discarded.

#ifndef AKVC_PROTOCOL_H
#define AKVC_PROTOCOL_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define AKVC_MAGIC          0x43564B41u   /* 'AKVC' little-endian */
#define AKVC_SCHEMA_VERSION 2u             /* bumped in Phase 3 for heartbeat */

#define AKVC_RING_SLOTS     4u

/* FourCC helpers */
#define AKVC_FOURCC(a, b, c, d) \
    ((uint32_t)(uint8_t)(a)        | \
     ((uint32_t)(uint8_t)(b) << 8) | \
     ((uint32_t)(uint8_t)(c) << 16)| \
     ((uint32_t)(uint8_t)(d) << 24))

#define AKVC_FOURCC_NV12    AKVC_FOURCC('N','V','1','2')
#define AKVC_FOURCC_YUY2    AKVC_FOURCC('Y','U','Y','2')
#define AKVC_FOURCC_RGB24   AKVC_FOURCC('R','G','B',' ')
#define AKVC_FOURCC_MJPG    AKVC_FOURCC('M','J','P','G')

/* Frame flags (bitfield) */
#define AKVC_FLAG_NONE          0x00000000u
#define AKVC_FLAG_KEYFRAME      0x00000001u
#define AKVC_FLAG_DISCONTINUITY 0x00000002u
#define AKVC_FLAG_PLACEHOLDER   0x00000004u
#define AKVC_FLAG_STALE         0x00000008u
#define AKVC_FLAG_ERROR         0x00000010u

/* Frame header — 80 bytes, packed (no padding) to match Python struct '<...'.
 * Field order is chosen so that, even at pack(1), all uint64 reads land on
 * naturally aligned addresses (offset % 8 == 0) when the struct itself sits
 * at an 8-byte aligned slot start. */
#pragma pack(push, 1)
typedef struct akvc_frame_header {
    uint32_t magic;            /* AKVC_MAGIC                   off  0 */
    uint32_t schema_version;   /* AKVC_SCHEMA_VERSION          off  4 */
    uint32_t fourcc;           /* AKVC_FOURCC_*                off  8 */
    uint32_t width;            /*                              off 12 */
    uint32_t height;           /*                              off 16 */
    uint32_t stride[2];        /* plane strides (bytes)        off 20,24 */
    uint32_t plane_offset[2];  /* byte offset from slot start  off 28,32 */
    uint32_t plane_size[2];    /* size in bytes of plane[i]    off 36,40 */
    uint32_t flags;            /* AKVC_FLAG_*                  off 44 */
    uint64_t pts_100ns;        /* 100ns ticks, monotonic       off 48 */
    uint64_t seq_head;         /* seq at write start           off 56 */
    uint64_t seq_tail;         /* seq at write end             off 64 */
    uint32_t reserved[2];      /*                              off 72,76 */
                               /* total size: 80 bytes */
} akvc_frame_header_t;
#pragma pack(pop)

/* Ring control block — placed at the start of the shared region. */
#pragma pack(push, 8)
typedef struct akvc_ring_control {
    uint32_t magic;            /* AKVC_MAGIC */
    uint32_t schema_version;   /* AKVC_SCHEMA_VERSION */
    uint32_t slot_count;       /* AKVC_RING_SLOTS */
    uint32_t slot_size;        /* bytes per slot, including header + planes */
    uint64_t producer_seq;     /* monotonically increasing; slot index = (seq - 1) % slots */
    uint32_t writer_pid;       /* PID of the process that last wrote a frame */
    uint32_t consumer_count;   /* informational; bumped/decremented by readers */
    uint64_t created_pts_100ns;
    uint64_t producer_heartbeat; /* 100ns ticks; updated by producer every frame or every 1s */
    uint32_t helper_pid;        /* PID of the Helper process, or 0 */
    uint32_t helper_reserved;   /* reserved for future use */
    uint8_t  pad[72];           /* reserve to 128 bytes */
} akvc_ring_control_t;
#pragma pack(pop)

/* Default slot size = NV12 1080p + header rounded up to 16 KiB.
 * 1920 * 1080 * 3 / 2 = 3,110,400 bytes. With header (64) and padding to
 * 4 KiB pages we use 3,112,960. Round up to 0x300000 = 3,145,728 (3 MiB). */
#define AKVC_DEFAULT_SLOT_SIZE  0x00300000u

/* Total shared region size for the default ring. */
#define AKVC_DEFAULT_REGION_SIZE                                            \
    ((uint32_t)(sizeof(akvc_ring_control_t)) +                              \
     AKVC_DEFAULT_SLOT_SIZE * AKVC_RING_SLOTS)

/* Names of named kernel objects (Windows). We use the "Global" prefix so the
 * objects are visible across sessions: the producer (helper) runs in the user
 * session, while the MF frame server (frameserver.exe) runs in session 0.
 * "Local\" objects are per-session and would be invisible to the frame server.
 * Creating "Global" objects requires SeCreateGlobalPrivilege, which an
 * elevated (admin) helper has. */
#define AKVC_SHM_NAME       "Global\\akvc-frames-v1"
#define AKVC_EVENT_NAME     "Global\\akvc-frames-evt-v1"
#define AKVC_MUTEX_NAME     "Global\\akvc-frames-mtx-v1"
#define AKVC_FRAMEBUS_PATH_ENV "AKVC_FRAMEBUS_PATH"
#define AKVC_FRAMEBUS_DIR_ENV  "AKVC_FRAMEBUS_DIR"
#define AKVC_FRAMEBUS_DEFAULT_SUBDIR "AKVirtualCamera"
#define AKVC_FRAMEBUS_DEFAULT_FILE   "akvc-frames-v1.bin"

/* Helper service control pipe (Windows). */
#define AKVC_HELPER_PIPE    "\\\\.\\pipe\\akvc-helper-ctrl"

/* ---- macOS (Phase 4) ----
 * POSIX shared-memory region name. The Python producer (camera-core
 * frame_sink/macos_shm.py) creates this region with shm_open + 0666; the
 * Camera Extension (CoreMediaIO System Extension) opens it read-only via
 * the C shim framebus_posix.c.
 *
 * NOTE on the extension sandbox: whether a Camera Extension is permitted
 * to shm_open() a user-process-created region is the #1 unverified risk
 * of Phase 4. If the sandbox blocks it, the fallback is XPC + IOSurface
 * (Apple-sanctioned) — see docs/phase4/implementation-plan.md Plan B.
 *
 * NOTE on the heartbeat time base: macOS uses CLOCK_REALTIME 100ns ticks
 * (Unix epoch), NOT Windows FILETIME (1601 epoch). Producer
 * (Python: time.time_ns()//100) and consumer (C: clock_gettime
 * CLOCK_REALTIME / 100) must share this base. The producer_heartbeat
 * field is "same-side, same-source 100ns ticks"; it is NOT required to
 * match the Windows time base across platforms. */
#define AKVC_POSIX_SHM_NAME "/akvc-frames-v1"

/* Helper heartbeat interval: producer must update heartbeat at least this
 * often (in 100ns ticks). If helper_pid is set and heartbeat is stale for
 * longer than this, the helper publishes placeholder frames. */
#define AKVC_HEARTBEAT_INTERVAL (50ULL * 10000ULL)   /* 50 ms in 100ns ticks */
#define AKVC_HEARTBEAT_TIMEOUT  (500ULL * 10000ULL)  /* 500 ms timeout */

#ifdef __cplusplus
} /* extern "C" */
#endif

#endif /* AKVC_PROTOCOL_H */
