// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef void* akvc_macos_direct_sender_ref;

akvc_macos_direct_sender_ref akvc_macos_direct_sender_create(
    int width,
    int height,
    double fps,
    char* error_message,
    size_t error_capacity
);

void akvc_macos_direct_sender_destroy(akvc_macos_direct_sender_ref sender);

int akvc_macos_direct_sender_start(
    akvc_macos_direct_sender_ref sender,
    const char* camera_name,
    char* error_message,
    size_t error_capacity
);

int akvc_macos_direct_sender_send_bgr24(
    akvc_macos_direct_sender_ref sender,
    const void* data,
    int width,
    int height,
    int bytes_per_row,
    uint64_t pts_100ns,
    char* error_message,
    size_t error_capacity
);

int akvc_macos_direct_sender_send_bgra32(
    akvc_macos_direct_sender_ref sender,
    const void* data,
    int width,
    int height,
    int bytes_per_row,
    uint64_t pts_100ns,
    char* error_message,
    size_t error_capacity
);

int akvc_macos_direct_sender_consumer_count(akvc_macos_direct_sender_ref sender);

int akvc_macos_direct_sender_list_devices_json(
    char* json_buffer,
    size_t json_capacity,
    char* error_message,
    size_t error_capacity
);

int akvc_macos_direct_sender_request_camera_access_json(
    char* json_buffer,
    size_t json_capacity,
    char* error_message,
    size_t error_capacity
);

#ifdef __cplusplus
}
#endif
