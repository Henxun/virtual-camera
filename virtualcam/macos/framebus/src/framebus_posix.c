// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors
//
// AK Virtual Camera — Frame Bus POSIX consumer implementation.
// See framebus_posix.h for the contract and akvc_protocol.h for the schema.

#include "akvc/framebus_posix.h"

#include <errno.h>
#include <fcntl.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#define AKVC_FB_TEAR_RETRIES 5

struct akvc_fb_consumer {
    int      fd;
    uint8_t* base;            /* mapped region, read-only */
    uint32_t region_size;
    uint64_t last_seen_seq;   /* last seq handed out to the caller */
};

/* CLOCK_REALTIME in 100ns ticks (Unix epoch). Matches the Python producer. */
static uint64_t now_100ns_clock_realtime(void) {
    struct timespec ts;
    if (clock_gettime(CLOCK_REALTIME, &ts) != 0) {
        return 0;
    }
    return (uint64_t)ts.tv_sec * 10000000ULL + (uint64_t)ts.tv_nsec / 100ULL;
}

static const akvc_ring_control_t* ctrl(const akvc_fb_consumer_t* c) {
    return (const akvc_ring_control_t*)(void*)c->base;
}

static const uint8_t* slot_ptr(const akvc_fb_consumer_t* c, uint32_t index) {
    return c->base
         + sizeof(akvc_ring_control_t)
         + (size_t)index * AKVC_DEFAULT_SLOT_SIZE;
}

akvc_status_t akvc_fb_open(akvc_fb_consumer_t** out) {
    if (!out) return E_AKVC_INVALID_ARGUMENT;
    *out = NULL;

    akvc_fb_consumer_t* c = (akvc_fb_consumer_t*)calloc(1, sizeof(*c));
    if (!c) return E_AKVC_INTERNAL;
    c->fd = -1;

    int fd = shm_open(AKVC_POSIX_SHM_NAME, O_RDONLY, 0);
    if (fd < 0) {
        free(c);
        return E_AKVC_FRAMEBUS_OPEN_FAILED;
    }

    /* Determine the region size via fstat (the producer ftruncates it). */
    struct stat st;
    if (fstat(fd, &st) != 0 || st.st_size <= 0) {
        close(fd);
        free(c);
        return E_AKVC_FRAMEBUS_OPEN_FAILED;
    }
    c->fd = fd;
    c->region_size = (uint32_t)st.st_size;

    void* p = mmap(NULL, c->region_size, PROT_READ, MAP_SHARED, fd, 0);
    if (p == MAP_FAILED) {
        close(fd);
        free(c);
        return E_AKVC_FRAMEBUS_SCHEMA_MISMATCH;  /* mmap failed */
    }
    c->base = (uint8_t*)p;

    const akvc_ring_control_t* cb = ctrl(c);
    if (cb->magic != AKVC_MAGIC
        || cb->schema_version != AKVC_SCHEMA_VERSION
        || cb->slot_count != AKVC_RING_SLOTS
        || cb->slot_size != AKVC_DEFAULT_SLOT_SIZE) {
        munmap(c->base, c->region_size);
        close(c->fd);
        free(c);
        return E_AKVC_FRAMEBUS_SCHEMA_MISMATCH;
    }

    *out = c;
    return AKVC_OK;
}

void akvc_fb_close(akvc_fb_consumer_t* c) {
    if (!c) return;
    if (c->base && c->region_size) {
        munmap(c->base, c->region_size);
    }
    if (c->fd >= 0) close(c->fd);
    free(c);
}

akvc_status_t akvc_fb_poll(akvc_fb_consumer_t* c, akvc_fb_view_t* out) {
    if (!c || !out) return E_AKVC_INVALID_ARGUMENT;

    /* Re-read producer_seq atomically each attempt; the producer bumps it
     * AFTER finalizing seq_tail, so any seq we read here points at a slot
     * whose tail is (eventually) consistent. Tear-protection double-checks. */
    uint64_t seq = 0;
    for (int attempt = 0; attempt < AKVC_FB_TEAR_RETRIES; ++attempt) {
        seq = ctrl(c)->producer_seq;
        if (seq == 0) {
            return E_AKVC_FRAMEBUS_TIMEOUT;  /* producer hasn't written yet */
        }
        if (seq == c->last_seen_seq) {
            return E_AKVC_FRAMEBUS_TIMEOUT;  /* no new frame */
        }

        uint32_t slot_index = (uint32_t)((seq - 1) % AKVC_RING_SLOTS);
        const uint8_t* slot = slot_ptr(c, slot_index);
        const akvc_frame_header_t* hdr =
            (const akvc_frame_header_t*)(const void*)slot;

        /* Tear protection: head must equal tail AND equal the seq we read.
         * If the producer is mid-write (or advanced to another slot), retry. */
        if (hdr->magic != AKVC_MAGIC) continue;
        if (hdr->seq_head != seq) continue;
        if (hdr->seq_tail != seq) continue;

        /* Consistent frame. Hand out aliased pointers; caller must copy. */
        out->header = hdr;
        out->plane0 = slot + hdr->plane_offset[0];
        out->plane1 = (hdr->plane_size[1] > 0)
                        ? slot + hdr->plane_offset[1]
                        : NULL;
        out->seq    = seq;
        c->last_seen_seq = seq;
        return AKVC_OK;
    }
    return E_AKVC_FRAMEBUS_TORN_FRAME;
}

int akvc_fb_producer_alive(const akvc_fb_consumer_t* c) {
    if (!c) return 0;
    uint64_t hb = ctrl(c)->producer_heartbeat;
    if (hb == 0) return 0;
    uint64_t now = now_100ns_clock_realtime();
    if (now == 0) return 1;  /* clock read failed; don't false-negative */
    return (now - hb) < AKVC_HEARTBEAT_TIMEOUT ? 1 : 0;
}

uint64_t akvc_fb_producer_seq(const akvc_fb_consumer_t* c) {
    return c ? ctrl(c)->producer_seq : 0;
}
