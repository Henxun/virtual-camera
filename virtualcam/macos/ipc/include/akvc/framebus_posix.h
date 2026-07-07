// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors
//
// AK Virtual Camera — Frame Bus (macOS / POSIX)

#ifndef AKVC_FRAMEBUS_POSIX_H
#define AKVC_FRAMEBUS_POSIX_H

#include <stddef.h>
#include <stdint.h>

#include "akvc_errors.h"
#include "akvc_protocol.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct akvc_fb_view {
    const akvc_frame_header_t* header;
    const uint8_t* plane0;
    const uint8_t* plane1;
    uint64_t seq;
} akvc_fb_view_t;

typedef struct akvc_fb_consumer akvc_fb_consumer_t;

akvc_status_t akvc_fb_open_named(akvc_fb_consumer_t** out, const char* shm_name);
akvc_status_t akvc_fb_open(akvc_fb_consumer_t** out);
void akvc_fb_close(akvc_fb_consumer_t* c);
akvc_status_t akvc_fb_poll(akvc_fb_consumer_t* c, akvc_fb_view_t* out);
int akvc_fb_producer_alive(const akvc_fb_consumer_t* c);
uint64_t akvc_fb_producer_seq(const akvc_fb_consumer_t* c);
uint32_t akvc_fb_consumer_count(const akvc_fb_consumer_t* c);

#ifdef __cplusplus
}  // extern "C"
#endif

#endif  // AKVC_FRAMEBUS_POSIX_H
