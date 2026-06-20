# SPDX-License-Identifier: Apache-2.0

add_library(akvc_framebus STATIC
    src/framebus.cpp
    src/sddl_helper.cpp
)

target_include_directories(akvc_framebus
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include
        ${CMAKE_SOURCE_DIR}/virtualcam/shared
)

target_link_libraries(akvc_framebus PUBLIC
    advapi32   # ConvertStringSecurityDescriptorToSecurityDescriptorW
)

set_target_properties(akvc_framebus PROPERTIES
    POSITION_INDEPENDENT_CODE ON
    MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>"
)
