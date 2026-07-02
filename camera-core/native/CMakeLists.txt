# SPDX-License-Identifier: Apache-2.0

find_package(Python3 COMPONENTS Interpreter Development.Module REQUIRED)

set(AKVC_PYBIND11_CMAKEDIR "")
if(NOT pybind11_DIR)
    execute_process(
        COMMAND ${Python3_EXECUTABLE} -m pybind11 --cmakedir
        OUTPUT_VARIABLE AKVC_PYBIND11_CMAKEDIR
        OUTPUT_STRIP_TRAILING_WHITESPACE
        RESULT_VARIABLE AKVC_PYBIND11_CMAKEDIR_RESULT
    )
    if(AKVC_PYBIND11_CMAKEDIR_RESULT EQUAL 0 AND EXISTS "${AKVC_PYBIND11_CMAKEDIR}")
        set(pybind11_DIR "${AKVC_PYBIND11_CMAKEDIR}" CACHE PATH "pybind11 CMake config dir" FORCE)
    endif()
endif()

find_package(pybind11 CONFIG QUIET)
if(NOT pybind11_FOUND)
    if(AKVC_PYBIND11_CMAKEDIR AND EXISTS "${AKVC_PYBIND11_CMAKEDIR}")
        find_package(pybind11 CONFIG REQUIRED PATHS "${AKVC_PYBIND11_CMAKEDIR}" NO_DEFAULT_PATH)
    else()
        find_package(pybind11 CONFIG REQUIRED)
    endif()
endif()

pybind11_add_module(akvc_core_native MODULE
    src/module.cpp
    src/frame_types.cpp
    src/pipeline_ops.cpp
    src/metrics.cpp
    src/protocol.cpp
    src/providers/test_pattern_provider.cpp
    src/providers/usb_provider.cpp
    src/providers/provider_factory.cpp
    src/virtual_camera_session.cpp
    src/runtime_host.cpp
    src/sinks/windows_framebus.cpp
    src/sinks/macos_shm_sink.cpp
    src/helper/windows_helper_client.cpp
)

target_include_directories(akvc_core_native PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/include
    ${CMAKE_SOURCE_DIR}/virtualcam/windows/framebus/include
    ${CMAKE_SOURCE_DIR}/virtualcam/shared
)

target_link_libraries(akvc_core_native PRIVATE
    akvc_framebus
    Python3::Module
    advapi32
    shell32
    mf
    mfplat
    mfreadwrite
    mfuuid
    ole32
)

if(MSVC)
    target_compile_options(akvc_core_native PRIVATE /EHsc)
endif()

set_target_properties(akvc_core_native PROPERTIES
    OUTPUT_NAME "_core_native"
    PREFIX ""
    SUFFIX ".pyd"
    MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>"
)

install(TARGETS akvc_core_native
        RUNTIME DESTINATION akvc
        LIBRARY DESTINATION akvc)
