// SPDX-License-Identifier: Apache-2.0
#ifndef AKVC_MACOS_IPC_H
#define AKVC_MACOS_IPC_H

#include <stdint.h>
#include <stddef.h>

#include "akvc_protocol.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct akvc_macos_ring_descriptor {
    uint32_t slot_count;
    uint32_t slot_size;
    char shm_name[64];
} akvc_macos_ring_descriptor_t;

#define AKVC_MACOS_APP_GROUP_IDENTIFIER "group.com.sidus.amaran-desktop"
#define AKVC_MACOS_SHARED_STATE_DIR_ENV "AKVC_MACOS_SHARED_STATE_DIR"
#define AKVC_MACOS_SHARED_STATE_DIR_SUFFIX "Library/Group Containers/group.com.sidus.amaran-desktop/akvc-shared"
#define AKVC_MACOS_SHM_NAME_FILE_ENV "AKVC_MACOS_SHM_NAME_FILE"
#define AKVC_MACOS_SHM_NAME_FILE_NAME "akvc-macos-shm-name.txt"
#define AKVC_MACOS_SHM_NAME_ENV "AKVC_MACOS_SHM_NAME"
#define AKVC_MACOS_DEVICE_NAME_FILE_ENV "AKVC_DEVICE_NAME_FILE"
#define AKVC_MACOS_DEVICE_NAME_FILE_NAME "akvc-macos-device-name.txt"
#define AKVC_MACOS_DEVICE_NAME_ENV "AKVC_DEVICE_NAME"
#define AKVC_MACOS_DEMO_MODE_FILE_ENV "AKVC_MACOS_DEMO_MODE_FILE"
#define AKVC_MACOS_DEMO_MODE_FILE_NAME "akvc-macos-demo-mode.txt"
#define AKVC_MACOS_DEMO_MODE_ENV "AKVC_MACOS_DEMO_MODE"

void akvc_macos_ring_descriptor_default(akvc_macos_ring_descriptor_t* out_desc);
uint32_t akvc_macos_default_region_size(void);
const char* akvc_macos_resolved_device_name(void);
int akvc_macos_demo_mode_enabled(void);

#ifdef __cplusplus
}
#endif

#endif  // AKVC_MACOS_IPC_H
