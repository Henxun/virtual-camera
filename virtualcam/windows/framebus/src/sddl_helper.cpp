// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors
//
// SDDL helper for AK Virtual Camera Frame Bus.

#include "akvc/framebus.h"

#include <sddl.h>
#include <windows.h>

namespace akvc {

std::wstring build_framebus_sddl() {
    // D:dacl_flags(ace1)(ace2)...
    // GA = generic all, GR = generic read, GW = generic write
    // BA = BUILTIN\Administrators
    // SY = LOCAL_SYSTEM
    // AC = ALL APPLICATION PACKAGES (legacy alias for AppContainer set)
    // S-1-15-2-1 = ALL_APP_PACKAGES well-known SID (Win8+)
    // S-1-15-2-2 = ALL_RESTRICTED_APP_PACKAGES (some MF LowBox containers)
    return std::wstring(
        L"D:"
        L"(A;;GA;;;BA)"
        L"(A;;GA;;;SY)"
        L"(A;;GA;;;AU)"         // Authenticated Users (UI + worker processes)
        L"(A;;GRGW;;;AC)"
        L"(A;;GRGW;;;S-1-15-2-1)"
        L"(A;;GRGW;;;S-1-15-2-2)"
    );
}

}  // namespace akvc
