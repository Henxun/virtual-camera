# SPDX-License-Identifier: Apache-2.0
#
# AK Virtual Camera — DirectShow Source Filter
#
# Requires:
#  - Microsoft DirectShow BaseClasses, expected at:
#      ${AKVC_BASECLASSES_DIR} (default: third_party/baseclasses)
#    Build them once into:
#      ${AKVC_BASECLASSES_LIB}/strmbase.lib
#  - Windows SDK (strmiids, dxguid, ole32, oleaut32, advapi32, user32, winmm)
#
# tools/make.py configure handles the BaseClasses checkout and one-time build.

set(AKVC_BASECLASSES_DIR "${CMAKE_SOURCE_DIR}/third_party/baseclasses"
    CACHE PATH "Path to DirectShow BaseClasses sources")

# Header-only consumers may include headers from BaseClasses. The compiled
# library `strmbase.lib` (Release) is built separately by make.py.
set(AKVC_BASECLASSES_INCLUDE "${AKVC_BASECLASSES_DIR}")
set(AKVC_BASECLASSES_LIB
    "${CMAKE_SOURCE_DIR}/third_party/baseclasses/build/Release/strmbase.lib"
    CACHE FILEPATH "Path to compiled strmbase.lib")

if(NOT EXISTS "${AKVC_BASECLASSES_INCLUDE}/streams.h")
    message(FATAL_ERROR
        "DirectShow BaseClasses not found at ${AKVC_BASECLASSES_INCLUDE}.\n"
        "Run: python tools/make.py configure")
endif()

add_library(akvc_dshow SHARED
    src/dll_main.cpp
    src/cvcam_filter.cpp
    src/cvcam_stream.cpp
    src/registry.cpp
    resources/akvc.rc
    resources/akvc.def
)

set_target_properties(akvc_dshow PROPERTIES
    OUTPUT_NAME "akvc-dshow"
    SUFFIX ".dll"
    PREFIX ""
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin/dshow"
    MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>"
)

# BaseClasses headers (transitively included via streams.h) trip several
# warnings-as-errors on modern MSVC. Inherit the same relaxed options the
# strmbase static lib uses.
target_compile_options(akvc_dshow PRIVATE
    /permissive
    /wd4267 /wd4244 /wd4100 /wd4189 /wd4127 /wd4505 /wd4324
    /wd4456 /wd4457 /wd4458 /wd4459
    /wd4302 /wd4311 /wd4312 /wd4477 /wd4838 /wd4995 /wd4996
    /wd4596 /wd4359
)
target_compile_definitions(akvc_dshow PRIVATE
    _CRT_SECURE_NO_WARNINGS _SCL_SECURE_NO_WARNINGS
)

target_include_directories(akvc_dshow PRIVATE
    include
    ${CMAKE_SOURCE_DIR}/virtualcam/shared
    ${AKVC_BASECLASSES_INCLUDE}
)

target_link_libraries(akvc_dshow PRIVATE
    akvc_framebus
    "${AKVC_BASECLASSES_LIB}"
    strmiids
    dxguid
    winmm
    ole32
    oleaut32
    uuid
    advapi32
    user32
)

target_link_options(akvc_dshow PRIVATE
    "/DEF:${CMAKE_CURRENT_SOURCE_DIR}/resources/akvc.def"
)

# Group the filter and the framebus dependency in the install layout.
install(TARGETS akvc_dshow
        RUNTIME DESTINATION bin)
