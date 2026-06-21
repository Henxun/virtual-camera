// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors
//
// AK Virtual Camera — Frame Bus (macOS / POSIX)
//
// Plain-C consumer for the POSIX shared-memory ring defined in
// virtualcam/shared/akvc_protocol.h. The CoreMediaIO Camera Extension
// (Swift) calls this via a bridging header.
//
// Producer: camera-core frame_sink/macos_shm.py creates `/akvc-frames-v1`
//           with shm_open + 0o666 and writes NV12 frames + heartbeat.
// Consumer: this file — opened read-only by the Camera Extension process.
//
// Synchronization: NO cross-process event/mutex. The consumer polls at the
// stream frame rate and relies on the seq_head/seq_tail tear protection:
// every slot is written head→payload→tail; if head != tail on read, the
// slot is mid-write and is discarded. This mirrors the Windows consumer.
//
// Heartbeat time base: CLOCK_REALTIME 100ns ticks (Unix epoch) — matches
// the Python producer's time.time_ns()//100. NOT Windows FILETIME.

#ifndef AKVC_FRAMEBUS_POSIX_H
#define AKVC_FRAMEBUS_POSIX_H

#include <stdint.h>
#include <stddef.h>

#include "akvc_errors.h"
#include "akvc_protocol.h"

#ifdef __cplusplus
extern "C" {
#endif

/* A view into the current frame in the shared region. The pointers alias
 * the mapped memory and stay valid only until the next poll/close call.
 * The consumer (Swift) MUST copy the bytes out before yielding control. */
typedef struct akvc_fb_view {
    const akvc_frame_header_t* header;  /* may be NULL if no frame yet    */
    const uint8_t*             plane0;  /* Y plane (NV12) / packed (YUY2) */
    const uint8_t*             plane1;  /* UV plane (NV12); NULL otherwise */
    uint64_t                   seq;     /* seq of the frame this view is   */
} akvc_fb_view_t;

/* Opaque handle to an open frame-bus consumer. */
typedef struct akvc_fb_consumer akvc_fb_consumer_t;

/* Open the POSIX shared-memory region `/akvc-frames-v1` read-only.
 * Returns AKVC_OK on success, or an error code:
 *   E_AKVC_FRAMEBUS_OPEN_FAILED    — shm_open failed (region not created yet)
 *   E_AKVC_FRAMEBUS_SCHEMA_MISMATCH— mmap/map or magic/schema mismatch
 * On success *out is a heap-allocated handle; free with akvc_fb_close(). */
akvc_status_t akvc_fb_open(akvc_fb_consumer_t** out);

void akvc_fb_close(akvc_fb_consumer_t* c);

/* Non-blocking poll for a frame newer than the consumer's last-seen seq.
 * - If a fresh, non-torn frame is available: fills `out`, returns AKVC_OK.
 * - If no new frame yet: returns E_AKVC_FRAMEBUS_TIMEOUT, out untouched.
 * - If the slot is torn after AKVC_FB_TEAR_RETRIES retries: returns
 *   E_AKVC_FRAMEBUS_TORN_FRAME (caller should skip this tick).
 * The view aliases shared memory; copy before re-polling. */
akvc_status_t akvc_fb_poll(akvc_fb_consumer_t* c, akvc_fb_view_t* out);

/* Is the producer alive? Compares producer_heartbeat against CLOCK_REALTIME
 * now using AKVC_HEARTBEAT_TIMEOUT. Returns 1 if alive, 0 if stale/dead. */
int akvc_fb_producer_alive(const akvc_fb_consumer_t* c);

/* Current producer_seq (for diagnostics). */
uint64_t akvc_fb_producer_seq(const akvc_fb_consumer_t* c);

#ifdef __cplusplus
}  /* extern "C" */
#endif

#endif  /* AKVC_FRAMEBUS_POSIX_H */
