# SPDX-License-Identifier: Apache-2.0
#
# AK Virtual Camera — Helper Service
#
# Standalone executable that owns the Frame Bus shared memory and monitors
# the producer heartbeat. When the UI disconnects it publishes placeholder
# frames so consumers never see a frozen image.

set(AKVC_HELPER_SRC
    src/main.cpp
)

add_executable(akvc_helper ${AKVC_HELPER_SRC})

target_include_directories(akvc_helper PRIVATE
    include
    ${CMAKE_SOURCE_DIR}/virtualcam/shared
    ${CMAKE_SOURCE_DIR}/virtualcam/windows/framebus/include
)

target_link_libraries(akvc_helper PRIVATE
    akvc_framebus
    mfplat
    mfuuid
    mfsensorgroup
    ole32
    oleaut32
    advapi32
)

set_target_properties(akvc_helper PROPERTIES
    MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>"
)

install(TARGETS akvc_helper
        RUNTIME DESTINATION bin)
