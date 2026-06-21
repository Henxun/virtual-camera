// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors
//
// AK Virtual Camera — Helper Service
//
// Standalone process that owns the Frame Bus shared memory. It:
//   1. Creates the named file mapping, event, and mutex.
//   2. Listens on a named pipe (akvc-helper-ctrl) for control commands.
//   3. Monitors producer heartbeat; publishes placeholder (black) frames
//      when the UI producer goes away, so consumers never see a frozen frame.
//
// Lifecycle:
//   - Started by the desktop app (or CLI) on demand.
//   - Exits when it receives QUIT on the pipe, or stdin EOF, or CTRL+C.
//   - On crash the SHM is released by the OS (named objects persist until
//     last handle closes); consumers see a stale frame and eventually time
//     out.

#ifndef AKVC_HELPER_H
#define AKVC_HELPER_H

#include <atomic>
#include <cstdint>
#include <string>
#include <thread>

#include <windows.h>

#include <mfapi.h>
#include <mfidl.h>
#include <mfvirtualcamera.h>

#include "akvc/framebus.h"
#include "akvc_protocol.h"

namespace akvc {

// Maximum placeholder frames per second when UI is gone.
constexpr uint32_t kPlaceholderFps = 10;

// Pipe instance timeout (ms) before helper checks shutdown flag.
constexpr DWORD kPipeWaitTimeoutMs = 200;

class Helper {
public:
    Helper() = default;
    Helper(const Helper&) = delete;
    Helper& operator=(const Helper&) = delete;
    ~Helper();

    // Start the helper: create SHM, start pipe listener, enter heartbeat loop.
    // Returns false if SHM creation fails.
    bool start();

    // Register the MF virtual camera with Windows.
    bool register_mf_virtual_camera();

    // Signal the helper to stop. Thread-safe.
    void stop();

    // Block until the helper has fully stopped.
    void wait();

private:
    // Heartbeat monitor loop — runs in its own thread.
    void heartbeat_loop();

    // Pipe listener loop — runs in its own thread.
    void pipe_loop();

    // Handle one pipe client request.
    // Returns false if the pipe connection should be closed.
    bool handle_client(HANDLE pipe);

    // Publish a placeholder frame (black NV12 1280x720).
    void publish_placeholder();

    // --- state ---
    std::atomic<bool> running_{false};

    FrameBusProducer producer_;

    std::thread heartbeat_thread_;
    std::thread pipe_thread_;

    // The MF VirtualCamera reference. Held alive for the helper's lifetime so
    // the PnP device stays present; released (Stop + Remove) on shutdown so
    // no stale device node lingers.
    IMFVirtualCamera* mf_camera_ = nullptr;

    // When the UI last checked in (from heartbeat monitoring perspective).
    // If the UI process crashes, heartbeat_ will stop updating, and after
    // AKVC_HEARTBEAT_TIMEOUT we start publishing placeholders.
    bool ui_connected_ = false;
};

}  // namespace akvc

#endif  // AKVC_HELPER_H
