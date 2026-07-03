// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors
//
// Minimal JSON probe for the macOS POSIX Frame Bus consumer.

#include "akvc/framebus_posix.h"

#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

static uint64_t checksum_bytes(const uint8_t* data, uint32_t size) {
    uint64_t acc = 1469598103934665603ULL;
    for (uint32_t index = 0; index < size; ++index) {
        acc ^= (uint64_t)data[index];
        acc *= 1099511628211ULL;
    }
    return acc;
}

static void sleep_millis(unsigned int millis) {
    struct timespec ts;
    ts.tv_sec = (time_t)(millis / 1000U);
    ts.tv_nsec = (long)((millis % 1000U) * 1000000UL);
    nanosleep(&ts, NULL);
}

static const char* status_name(akvc_status_t status) {
    switch (status) {
        case AKVC_OK:
            return "ok";
        case E_AKVC_FRAMEBUS_OPEN_FAILED:
            return "open_failed";
        case E_AKVC_FRAMEBUS_SCHEMA_MISMATCH:
            return "schema_mismatch";
        case E_AKVC_FRAMEBUS_TIMEOUT:
            return "timeout";
        case E_AKVC_FRAMEBUS_TORN_FRAME:
            return "torn_frame";
        case E_AKVC_INVALID_ARGUMENT:
            return "invalid_argument";
        default:
            return "unexpected";
    }
}

int main(int argc, char** argv) {
    int attempts = 8;
    unsigned int sleep_ms = 25;
    const char* shm_name = AKVC_POSIX_SHM_NAME;

    for (int index = 1; index < argc; ++index) {
        if (strcmp(argv[index], "--attempts") == 0 && index + 1 < argc) {
            attempts = atoi(argv[++index]);
            continue;
        }
        if (strcmp(argv[index], "--sleep-ms") == 0 && index + 1 < argc) {
            sleep_ms = (unsigned int)strtoul(argv[++index], NULL, 10);
            continue;
        }
        if (strcmp(argv[index], "--shm-name") == 0 && index + 1 < argc) {
            shm_name = argv[++index];
            continue;
        }
    }

    if (attempts < 1) {
        attempts = 1;
    }

    akvc_fb_consumer_t* consumer = NULL;
    akvc_status_t open_status = akvc_fb_open_named(&consumer, shm_name);
    if (open_status != AKVC_OK) {
        int direct_errno = 0;
        int direct_fd = shm_open(shm_name, O_RDWR, 0);
        struct stat st = {};
        int stat_errno = 0;
        if (direct_fd >= 0) {
            if (fstat(direct_fd, &st) != 0) {
                stat_errno = errno;
            }
            close(direct_fd);
        } else {
            direct_errno = errno;
        }
        printf(
            "{"
            "\"status\":\"%s\","
            "\"status_code\":%d,"
            "\"shm_name\":\"%s\","
            "\"direct_open_errno\":%d,"
            "\"stat_errno\":%d,"
            "\"direct_size\":%" PRIuMAX
            "}\n",
            status_name(open_status),
            (int)open_status,
            shm_name,
            direct_errno,
            stat_errno,
            (uintmax_t)st.st_size
        );
        return 1;
    }

    akvc_status_t last_status = E_AKVC_FRAMEBUS_TIMEOUT;
    akvc_fb_view_t view = {};
    for (int attempt = 0; attempt < attempts; ++attempt) {
        last_status = akvc_fb_poll(consumer, &view);
        if (last_status == AKVC_OK) {
            break;
        }
        if (attempt + 1 < attempts) {
            sleep_millis(sleep_ms);
        }
    }

    if (last_status != AKVC_OK) {
        int producer_alive = akvc_fb_producer_alive(consumer);
        uint64_t producer_seq = akvc_fb_producer_seq(consumer);
        uint32_t consumer_count = akvc_fb_consumer_count(consumer);
        printf(
            "{\"status\":\"%s\",\"status_code\":%d,\"shm_name\":\"%s\",\"producer_alive\":%s,\"producer_seq\":%" PRIu64 ",\"consumer_count\":%u}\n",
            status_name(last_status),
            (int)last_status,
            shm_name,
            producer_alive ? "true" : "false",
            producer_seq,
            consumer_count
        );
        akvc_fb_close(consumer);
        return 2;
    }

    const akvc_frame_header_t* header = view.header;
    uint64_t plane0_checksum = checksum_bytes(view.plane0, header->plane_size[0]);
    uint64_t plane1_checksum = checksum_bytes(view.plane1, header->plane_size[1]);
    int producer_alive = akvc_fb_producer_alive(consumer);
    uint64_t producer_seq = akvc_fb_producer_seq(consumer);
    uint32_t consumer_count = akvc_fb_consumer_count(consumer);

    printf(
        "{"
        "\"status\":\"ok\","
        "\"status_code\":0,"
        "\"shm_name\":\"%s\","
        "\"producer_alive\":%s,"
        "\"producer_seq\":%" PRIu64 ","
        "\"consumer_count\":%u,"
        "\"view_seq\":%" PRIu64 ","
        "\"width\":%u,"
        "\"height\":%u,"
        "\"fourcc\":%u,"
        "\"flags\":%u,"
        "\"stride0\":%u,"
        "\"stride1\":%u,"
        "\"plane0_size\":%u,"
        "\"plane1_size\":%u,"
        "\"plane0_checksum\":%" PRIu64 ","
        "\"plane1_checksum\":%" PRIu64
        "}\n",
        shm_name,
        producer_alive ? "true" : "false",
        producer_seq,
        consumer_count,
        view.seq,
        header->width,
        header->height,
        header->fourcc,
        header->flags,
        header->stride[0],
        header->stride[1],
        header->plane_size[0],
        header->plane_size[1],
        plane0_checksum,
        plane1_checksum
    );

    akvc_fb_close(consumer);
    return 0;
}
