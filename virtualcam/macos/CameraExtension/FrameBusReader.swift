// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 AK Virtual Camera Authors
//
// AK Virtual Camera — FrameBusReader: Swift wrapper over framebus_posix.c.
//
// This is the bridge between the POSIX shared-memory ring and CoreVideo.
// The C consumer (akvc_fb_*) is imported via the bridging header. We copy
// the plane bytes out of shared memory into a CVPixelBuffer on each poll
// (no zero-copy: the shm region is not an IOSurface and the sandbox may
// not allow us to hand its raw bytes to a cross-process CVPixelBuffer).

import CoreFoundation
import CoreMedia
import CoreVideo
import Foundation

enum AKVCPollResult {
    case ok
    case timeout
    case torn
}

struct AKVCFrameView {
    var width: Int = 0
    var height: Int = 0
    var stride0: Int = 0
    var stride1: Int = 0
    var planeSize0: Int = 0
    var planeSize1: Int = 0
    var pts100ns: Int64 = 0
    var plane0: UnsafePointer<UInt8>? = nil
    var plane1: UnsafePointer<UInt8>? = nil
}

final class AKVCFrameBusReader {

    private var consumer: OpaquePointer? = nil  // akvc_fb_consumer_t*
    private var pixelBufferPool: CVPixelBufferPool? = nil

    /// Lazily-created format description for the fixed NV12 1280x720 format.
    /// Used both for the stream format and for CMSampleBuffer creation.
    private(set) var formatDescription: CMVideoFormatDescription? = nil

    private let width = 1280
    private let height = 720

    init() {
        var fd: CMVideoFormatDescription?
        CMVideoFormatDescriptionCreate(
            allocator: kCFAllocatorDefault,
            codecType: kCVPixelFormatType_420YpCbCr8BiPlanarVideoRange,
            width: Int32(width), height: Int32(height),
            extensions: nil,
            formatDescriptionOut: &fd
        )
        self.formatDescription = fd

        // Pool of NV12 pixel buffers we own (not backed by shm).
        let attrs: [CFString: Any] = [
            kCVPixelBufferPixelFormatTypeKey: kCVPixelFormatType_420YpCbCr8BiPlanarVideoRange,
            kCVPixelBufferWidthKey: width,
            kCVPixelBufferHeightKey: height,
            kCVPixelBufferIOSurfacePropertiesKey: [:] as CFDictionary,
        ]
        CVPixelBufferPoolCreate(kCFAllocatorDefault, nil, attrs as CFDictionary, &pixelBufferPool)
    }

    func open() throws {
        // VERIFY: the bridging-header C function is callable as
        // `akvc_fb_open(_:)` returning Int32 (akvc_status_t).
        var c: OpaquePointer? = nil
        let st = akvc_fb_open(&c)
        if st != 0 {  // AKVC_OK == 0
            os_log("akvc.ext.reader: akvc_fb_open failed st=%d", type: .error, st)
            throw NSError(domain: "AKVC", code: Int(st))
        }
        self.consumer = c
    }

    func close() {
        if let c = consumer {
            akvc_fb_close(c)
            consumer = nil
        }
    }

    func isProducerAlive -> Bool {
        guard let c = consumer else { return false }
        return akvc_fb_producer_alive(c) != 0
    }

    func poll(_ out: inout AKVCFrameView) -> AKVCPollResult {
        guard let c = consumer else { return .timeout }
        var view = akvc_fb_view_t()
        let st = akvc_fb_poll(c, &view)
        if st == 0 {  // AKVC_OK
            guard let hdr = view.header?.pointee else { return .torn }
            out.width      = Int(hdr.width)
            out.height     = Int(hdr.height)
            out.stride0    = Int(hdr.stride.0)
            out.stride1    = Int(hdr.stride.1)
            out.planeSize0 = Int(hdr.plane_size.0)
            out.planeSize1 = Int(hdr.plane_size.1)
            out.pts100ns   = hdr.pts_100ns
            out.plane0     = view.plane0
            out.plane1     = view.plane1
            return .ok
        }
        // VERIFY: the E_AKVC_FRAMEBUS_TORN_FRAME / TIMEOUT numeric values
        // map cleanly; if the import renames them, switch to symbolic checks.
        if st == -1003 { return .timeout }   // E_AKVC_FRAMEBUS_TIMEOUT
        if st == -1004 { return .torn }      // E_AKVC_FRAMEBUS_TORN_FRAME
        return .timeout
    }

    /// Copy the frame's planes into a pool-allocated CVPixelBuffer (NV12).
    func makePixelBuffer(from v: AKVCFrameView) -> CVPixelBuffer? {
        guard let pool = pixelBufferPool else { return nil }
        var pb: CVPixelBuffer?
        CVPixelBufferPoolCreatePixelBuffer(kCFAllocatorDefault, pool, &pb)
        guard let pixelBuffer = pb else { return nil }

        CVPixelBufferLockBaseAddress(pixelBuffer, [])
        defer { CVPixelBufferUnlockBaseAddress(pixelBuffer, []) }

        // Plane 0 (Y)
        if let ySrc = v.plane0, v.planeSize0 > 0 {
            let yDst = CVPixelBufferGetBaseAddressOfPlane(pixelBuffer, 0)
            let dstStride = CVPixelBufferGetBytesPerRowOfPlane(pixelBuffer, 0)
            copyPlane(src: ySrc, srcStride: v.stride0,
                      dst: yDst, dstStride: dstStride,
                      height: v.height, planeSize: v.planeSize0)
        }
        // Plane 1 (UV, half height for NV12)
        if let uvSrc = v.plane1, v.planeSize1 > 0 {
            let uvDst = CVPixelBufferGetBaseAddressOfPlane(pixelBuffer, 1)
            let dstStride = CVPixelBufferGetBytesPerRowOfPlane(pixelBuffer, 1)
            copyPlane(src: uvSrc, srcStride: v.stride1,
                      dst: uvDst, dstStride: dstStride,
                      height: v.height / 2, planeSize: v.planeSize1)
        }
        return pixelBuffer
    }

    private func copyPlane(src: UnsafePointer<UInt8>, srcStride: Int,
                           dst: UnsafeMutableRawPointer?, dstStride: Int,
                           height: Int, planeSize: Int) {
        guard let dst = dst else { return }
        // Row-by-row copy to respect the destination stride (which the
        // framework may pad differently than our ring).
        let rowBytes = min(srcStride, dstStride)
        for row in 0..<height {
            let s = src.advanced(by: row * srcStride)
            let d = dst.advanced(by: row * dstStride)
                .assumingMemoryBound(to: UInt8.self)
            memcpy(d, s, rowBytes)
        }
    }

    /// Publish a black NV12 placeholder (called when the producer is dead).
    func publishPlaceholder(into stream: AKVCStream) {
        // VERIFY: this needs the same CMSampleBuffer path as Stream.pushFrame.
        // For the scaffold we leave it as a hook; implement alongside the
        // frame-delivery VERIFY in Stream.swift.
        // FIXME(Phase 4): emit a black CVPixelBuffer + CMSampleBuffer via the
        // stream's (verified) delivery API, with flags=PLACEHOLDER.
    }
}
