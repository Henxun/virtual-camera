# SPDX-License-Identifier: Apache-2.0
# AK Virtual Camera — control layer (pure C++ core + ObjC++ macOS backends).
#
# Produces:
#   akvc_camera_core     — platform-agnostic frame types + pipeline primitives
#   akvc_camera_windows  — Windows runtime session (helper client + framebus producer)
#   akvc_camera_tests    — cross-platform pipeline tests
#   akvc_camera_windows_tests — Windows session smoke tests

# ---- akvc_camera_core: types + raw-buffer pipeline algorithms ---------------
add_library(akvc_camera_core STATIC
    src/pipeline_ops.cpp
    src/format_status.cpp
)
target_include_directories(akvc_camera_core PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)
target_compile_features(akvc_camera_core PUBLIC cxx_std_17)
if(MSVC)
    target_compile_options(akvc_camera_core PRIVATE /W3 /utf-8 /EHsc)
endif()

# ---- akvc_camera_windows: Windows runtime session ---------------------------
if(WIN32)
    add_library(akvc_camera_windows STATIC
        src/platform/windows/helper_client_runtime.cpp
        src/platform/windows/framebus_producer.cpp
        src/platform/windows/windows_session.cpp
    )
    target_link_libraries(akvc_camera_windows PUBLIC
        akvc_camera_core
        akvc_framebus
        advapi32
        shell32
    )
    target_include_directories(akvc_camera_windows PRIVATE
        ${CMAKE_SOURCE_DIR}/virtualcam/windows/framebus/include
        ${CMAKE_SOURCE_DIR}/virtualcam/shared
    )
    if(MSVC)
        target_compile_options(akvc_camera_windows PRIVATE /W3 /utf-8 /EHsc)
    endif()
endif()

# ---- akvc_camera_macos: macOS runtime session (ObjC++) ---------------------
# BLOCKED on this environment (no Mac). Built only on APPLE. Source list is the
# transitive set reused from virtualcam/macos/; may need finalization on Mac.
if(APPLE)
    enable_language(OBJCXX)
    add_library(akvc_camera_macos STATIC
        src/platform/macos/macos_session.mm
        ${CMAKE_SOURCE_DIR}/virtualcam/macos/direct_sender/AKVCDirectCameraSender.mm
        ${CMAKE_SOURCE_DIR}/virtualcam/macos/control_bridge/AKVCSystemExtensionSupport.mm
        ${CMAKE_SOURCE_DIR}/virtualcam/macos/control_bridge/AKVCCommandSupport.mm
        ${CMAKE_SOURCE_DIR}/virtualcam/macos/ipc/src/macos_ipc.cpp
        ${CMAKE_SOURCE_DIR}/virtualcam/macos/ipc/src/framebus_posix.c
    )
    target_link_libraries(akvc_camera_macos PUBLIC
        akvc_camera_core
        "-framework Foundation"
        "-framework AVFoundation"
        "-framework CoreMedia"
        "-framework CoreMediaIO"
        "-framework CoreVideo"
        "-framework SystemExtensions"
    )
    target_include_directories(akvc_camera_macos PRIVATE
        ${CMAKE_SOURCE_DIR}/virtualcam/macos/direct_sender
        ${CMAKE_SOURCE_DIR}/virtualcam/macos/control_bridge
        ${CMAKE_SOURCE_DIR}/virtualcam/macos/ipc/include
        ${CMAKE_SOURCE_DIR}/virtualcam/shared
    )
    target_compile_features(akvc_camera_macos PUBLIC cxx_std_17)
endif()

# ---- akvc_camera: public facade library (third-party entry point) -----------
add_library(akvc_camera STATIC
    src/virtual_camera.cpp
)
target_link_libraries(akvc_camera PUBLIC akvc_camera_core)
if(WIN32)
    target_link_libraries(akvc_camera PUBLIC akvc_camera_windows)
elseif(APPLE)
    target_link_libraries(akvc_camera PUBLIC akvc_camera_macos)
endif()
target_compile_features(akvc_camera PUBLIC cxx_std_17)
if(MSVC)
    target_compile_options(akvc_camera PRIVATE /W3 /utf-8 /EHsc)
endif()

# ---- akvc_camera_python: thin pybind11 binding for apps/desktop ------------
# Built on Windows AND macOS - the desktop app drives the C++ layer via this
# binding on both platforms. (Linux would work too if a session is added.)
if(WIN32 OR APPLE)
    find_package(Python3 COMPONENTS Interpreter Development.Module REQUIRED)
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
    find_package(pybind11 CONFIG REQUIRED)
    pybind11_add_module(akvc_camera_python bindings/python/module.cpp)
    target_link_libraries(akvc_camera_python PRIVATE akvc_camera)
    target_include_directories(akvc_camera_python PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/include)
    if(WIN32)
        set_target_properties(akvc_camera_python PROPERTIES
            OUTPUT_NAME "akvc_camera"
            PREFIX ""
            SUFFIX ".pyd"
            # Route the module's import-library byproduct to a separate dir so it
            # does not collide with the akvc_camera static lib of the same basename.
            ARCHIVE_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lib_py"
            MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>"
        )
    else()
        # macOS: pybind11_add_module sets the Python extension suffix (.so).
        set_target_properties(akvc_camera_python PROPERTIES
            OUTPUT_NAME "akvc_camera"
            PREFIX ""
        )
    endif()
endif()

# ---- Tests (self-contained, no external framework) -------------------------
add_executable(akvc_camera_tests tests/test_pipeline_ops.cpp)
target_link_libraries(akvc_camera_tests PRIVATE akvc_camera_core)
if(MSVC)
    target_compile_options(akvc_camera_tests PRIVATE /W3 /utf-8 /EHsc)
endif()
add_test(NAME akvc_camera_pipeline_tests COMMAND akvc_camera_tests)

add_executable(akvc_camera_facade_tests tests/test_virtual_camera.cpp)
target_link_libraries(akvc_camera_facade_tests PRIVATE akvc_camera)
if(MSVC)
    target_compile_options(akvc_camera_facade_tests PRIVATE /W3 /utf-8 /EHsc)
endif()
add_test(NAME akvc_camera_facade_tests COMMAND akvc_camera_facade_tests)

if(WIN32)
    add_executable(akvc_camera_windows_tests tests/test_windows_session.cpp)
    target_link_libraries(akvc_camera_windows_tests PRIVATE akvc_camera_windows)
    if(MSVC)
        target_compile_options(akvc_camera_windows_tests PRIVATE /W3 /utf-8 /EHsc)
    endif()
    add_test(NAME akvc_camera_windows_session_tests COMMAND akvc_camera_windows_tests)
endif()

# ---- Match the project's static-CRT (/MT) convention used by framebus/native ----
if(MSVC)
    set(AKVC_CAMERA_RUNTIME "MultiThreaded$<$<CONFIG:Debug>:Debug>")
    foreach(t akvc_camera_core akvc_camera akvc_camera_tests akvc_camera_facade_tests)
        set_target_properties(${t} PROPERTIES MSVC_RUNTIME_LIBRARY "${AKVC_CAMERA_RUNTIME}")
    endforeach()
    if(WIN32)
        foreach(t akvc_camera_windows akvc_camera_windows_tests)
            set_target_properties(${t} PROPERTIES MSVC_RUNTIME_LIBRARY "${AKVC_CAMERA_RUNTIME}")
        endforeach()
    endif()
endif()
