// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors
//
// AK Virtual Camera — Camera Extension stream (Phase 4 scaffold, VERIFY).
//
// The stream owns a 30 fps dispatch timer that polls the POSIX frame bus
// and pushes each fresh frame to clients as a CMSampleBuffer.
//
// BIGGEST VERIFY SURFACE in the whole scaffold: the exact
// CMIOExtensionStream API to (a) advance the clock and (b) deliver a
// CMSampleBuffer to clients. Both are marked below. Confirm against the
// Apple "CameraExtension" sample and CMIOExtensionStream.h.

import CoreMediaIO
import CoreMedia
import CoreVideo
import Foundation

final class AKVCStream: CMIOExtensionStream {

    private let reader = AKVCFrameBusReader()
    private var timer: DispatchSourceTimer?
    private let queue = DispatchQueue(label: "com.akvc.ext.stream")

    /// VERIFY: CMIOExtensionClock usage. Apple's sample creates a clock and
    /// calls `resume()` on start / `pause()` on stop. Confirm the advance
    /// mechanism (does the framework pull via consumeClockValue, or does the
    /// extension push?). For now we create + resume/pause.
    private let clock = CMIOExtensionClock()

    init(localizedName: String, streamUID: String) throws {
        // NV12 1280x720@30. VERIFY the codec/pixel format constant:
        // kCVPixelFormatType_420YpCbCr8BiPlanarVideoRange ('420v') is NV12.
        var formatDescription: CMVideoFormatDescription?
        // VERIFY: CMVideoFormatDescriptionCreate signature + codecType.
        // For camera extensions the format is described by a pixel-format
        // based description, not an encoded codec type.
        CMVideoFormatDescriptionCreate(
            allocator: kCFAllocatorDefault,
            codecType: kCVPixelFormatType_420YpCbCr8BiPlanarVideoRange,
            width: 1280, height: 720,
            extensions: nil,
            formatDescriptionOut: &formatDescription
        )
        guard let desc = formatDescription else {
            os_log("akvc.ext.stream: formatDescription create failed", type: .error)
            throw NSError(domain: "AKVC", code: 1)
        }

        // VERIFY: CMIOExtensionStreamFormat initializer name + parameters.
        let streamFormat = CMIOExtensionStreamFormat(
            formatDescription: desc,
            maxFrameDuration: CMTime(value: 1, timescale: 30)
        )

        // VERIFY: super.init signature (localizedName/streamUID/streamFormat/
        // properties). Confirm against CMIOExtensionStream.h.
        super.init(localizedName: localizedName,
                   streamUID: streamUID,
                   streamFormat: streamFormat,
                   properties: [:])
    }

    override func start() throws {
        os_log("akvc.ext.stream.start", type: .info)
        try reader.open()

        // VERIFY: clock.resume() exists and is the right start call.
        clock.resume()

        let t = DispatchSource.makeTimerSource(queue: queue)
        t.schedule(deadline: .now(), repeating: .milliseconds(33))  // ~30 fps
        t.setEventHandler { [weak self] in self?.tick() }
        t.resume()
        timer = t
    }

    override func stop() {
        os_log("akvc.ext.stream.stop", type: .info)
        timer?.cancel()
        timer = nil
        reader.close()
        // VERIFY: clock.pause() exists.
        clock.pause()
    }

    override func formatChanged(to format: CMIOExtensionStreamFormat) {
        // No-op for MVP — we publish a single fixed NV12 format.
    }

    /// VERIFY: the framework may call this to synchronize; signature unknown
    /// offline. If the API requires implementing `consumeClockValue`, fill it
    /// in per CMIOExtensionStream.h. Left as an override placeholder.
    // override func consumeClockValue(_ clockValue: CMIOExtensionClock) { }

    // ---- frame pump ----

    private func tick() {
        // If the producer is gone, publish a black placeholder so the device
        // stays alive (mirrors the Windows helper behaviour, invariant I3).
        if !reader.isProducerAlive {
            pushPlaceholder()
            return
        }

        var view: AKVCFrameView = .init()
        switch reader.poll(&view) {
        case .ok:
            pushFrame(view: view)
        case .timeout:
            // No new frame this tick — skip (client keeps last frame).
            break
        case .torn:
            os_log("akvc.ext.stream: torn frame, skipping", type: .debug)
        }
    }

    private func pushFrame(view: AKVCFrameView) {
        guard let pixelBuffer = reader.makePixelBuffer(from: view) else { return }

        // VERIFY: timestamp source. Apple sample uses the clock's time or
        // CMClockGetHostTimeClock. Using the frame header's pts.
        let pts = CMTime(value: CMTimeValue(view.pts100ns),
                         timescale: 10_000_000)  // 100ns → seconds

        // VERIFY: CMSampleBuffer wrapping of an image buffer. The standard
        // recipe is CMSampleBufferCreateReadyWithImageBuffer.
        var sampleTiming = CMSampleTimingInfo(
            duration: CMTime(value: 1, timescale: 30),
            presentationTimeStamp: pts,
            decodeTimeStamp: pts
        )
        var sampleBuffer: CMSampleBuffer?
        CMSampleBufferCreateReadyWithImageBuffer(
            allocator: kCFAllocatorDefault,
            imageBuffer: pixelBuffer,
            formatDescription: reader.formatDescription,
            sampleTimingEntryCount: 1,
            sampleTimingArray: &sampleTiming,
            sampleBufferOut: &sampleBuffer
        )
        guard let sb = sampleBuffer else {
            os_log("akvc.ext.stream: sample buffer create failed", type: .error)
            return
        }

        // >>> VERIFY (biggest unknown): the exact CMIOExtensionStream API to
        // deliver a CMSampleBuffer to clients. Best guess below is
        // `sendNotification(_:parameter:)` with a notification case that
        // carries the sample buffer. Confirm the enum case name against
        // CMIOExtensionStream.h / the Apple sample and replace accordingly.
        // self.sendNotification(.streamConfigurationChanged, parameter: sb)  // ← WRONG, placeholder
        _ = sb  // remove once the real delivery call is wired
    }

    private func pushPlaceholder() {
        // Black 1280x720 NV12 frame. Reuses reader's allocator path.
        reader.publishPlaceholder(into: self)
    }
}
