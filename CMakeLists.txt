cmake_minimum_required(VERSION 3.25)
project(akvirtualcamera
    VERSION 0.2.0
    DESCRIPTION "AK Virtual Camera"
    LANGUAGES CXX)

# ---- Global settings ----
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "" FORCE)
endif()

# Always build x64 in Phase 2.
if(WIN32)
    if(NOT CMAKE_GENERATOR_PLATFORM AND CMAKE_GENERATOR MATCHES "Visual Studio")
        message(STATUS "Defaulting CMAKE_GENERATOR_PLATFORM to x64")
    endif()
endif()

# ---- Compile options ----
if(MSVC)
    # Note: /permissive- is intentionally NOT set globally. The DirectShow
    # BaseClasses sources (third_party/baseclasses) require /permissive to
    # compile under modern MSVC. Per-target options pick the right mode.
    add_compile_options(/W3 /Zc:__cplusplus /Zc:preprocessor /utf-8)
    add_compile_definitions(
        _WIN32_WINNT=0x0A00
        WINVER=0x0A00
        NOMINMAX
        WIN32_LEAN_AND_MEAN
        UNICODE _UNICODE)
endif()

# ---- Output layout ----
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")
set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lib")

# ---- Subprojects (Windows only in Phase 2) ----
if(WIN32)
    add_subdirectory(virtualcam/windows/framebus)
    add_subdirectory(virtualcam/windows/dshow)
    add_subdirectory(virtualcam/windows/helper)
    add_subdirectory(virtualcam/windows/mf)
endif()

message(STATUS "AKVC version: ${PROJECT_VERSION}")
message(STATUS "Build type:   ${CMAKE_BUILD_TYPE}")
message(STATUS "Generator:    ${CMAKE_GENERATOR}")
