// SPDX-License-Identifier: Apache-2.0
// AK Virtual Camera — version & device identity.

#ifndef AKVC_VERSION_H
#define AKVC_VERSION_H

#define AKVC_VERSION_MAJOR  0
#define AKVC_VERSION_MINOR  2
#define AKVC_VERSION_PATCH  0
#define AKVC_VERSION_STRING "0.2.0"

/* Device identity — keep stable across releases. */
#define AKVC_DEVICE_FRIENDLY_NAME_W L"AK Virtual Camera"
#define AKVC_DEVICE_VENDOR_W        L"AK"
#define AKVC_DEVICE_PRODUCT_ID_W    L"AKVC0001"

/* COM CLSID for the DirectShow Source Filter.
 *   {8E14549A-DB61-4309-AFA1-3578E927E933}
 * The byte ordering for DEFINE_GUID matches Windows guiddef.h.
 * Keep this CLSID constant; it is part of the public ABI. */
#define AKVC_DSHOW_FILTER_CLSID_GUID_STR L"{8E14549A-DB61-4309-AFA1-3578E927E933}"

#endif /* AKVC_VERSION_H */
