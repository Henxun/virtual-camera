// SPDX-License-Identifier: Apache-2.0
// AK Virtual Camera — error codes (cross-platform).

#ifndef AKVC_ERRORS_H
#define AKVC_ERRORS_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef int32_t akvc_status_t;

#define AKVC_OK                                  0

/* Frame Bus */
#define E_AKVC_FRAMEBUS_OPEN_FAILED            -1001
#define E_AKVC_FRAMEBUS_SCHEMA_MISMATCH        -1002
#define E_AKVC_FRAMEBUS_TIMEOUT                -1003
#define E_AKVC_FRAMEBUS_TORN_FRAME             -1004
#define E_AKVC_FRAMEBUS_NO_PRODUCER            -1005
#define E_AKVC_FRAMEBUS_PUBLISH_FAILED         -1006

/* Helper / IPC */
#define E_AKVC_HELPER_NOT_RUNNING              -2001
#define E_AKVC_HELPER_TIMEOUT                  -2002
#define E_AKVC_HELPER_BAD_REQUEST              -2003

/* Registration */
#define E_AKVC_REG_DSHOW_REGSVR_FAILED         -3001
#define E_AKVC_REG_MF_ACTIVATE_FAILED          -3002
#define E_AKVC_REG_MAC_EXT_REJECTED            -3003

/* Format */
#define E_AKVC_FORMAT_NOT_SUPPORTED            -4001

/* Device */
#define E_AKVC_DEVICE_BUSY                     -5001

/* Config */
#define E_AKVC_CONFIG_INVALID                  -6001

/* Generic */
#define E_AKVC_INVALID_ARGUMENT                -9001
#define E_AKVC_INTERNAL                        -9999

#ifdef __cplusplus
} /* extern "C" */
#endif

#endif /* AKVC_ERRORS_H */
