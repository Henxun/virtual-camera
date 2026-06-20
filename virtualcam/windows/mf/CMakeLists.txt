# SPDX-License-Identifier: Apache-2.0
#
# AK Virtual Camera — MF Virtual Camera Media Source

set(AKVC_MF_SRC
    src/mf_source.cpp
)

add_library(akvc_mf SHARED ${AKVC_MF_SRC})

target_compile_definitions(akvc_mf PRIVATE
    INITGUID
    _CRT_SECURE_NO_WARNINGS
)

set_target_properties(akvc_mf PROPERTIES
    OUTPUT_NAME "akvc-mf"
    SUFFIX ".dll"
    PREFIX ""
    MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>"
)

target_include_directories(akvc_mf PRIVATE
    include
    ${CMAKE_SOURCE_DIR}/virtualcam/shared
    ${CMAKE_SOURCE_DIR}/virtualcam/windows/framebus/include
)

target_link_libraries(akvc_mf PRIVATE
    akvc_framebus
    mfplat
    mfuuid
    mfsensorgroup
    ole32
    advapi32
)

target_link_options(akvc_mf PRIVATE
    "/DEF:${CMAKE_CURRENT_SOURCE_DIR}/resources/akvc-mf.def"
)

install(TARGETS akvc_mf RUNTIME DESTINATION bin)
