#!/usr/bin/env python3
"""
BUGSI Hardware Verification: IDS RGB Camera (via ids_peak)

Initialises the ids_peak library, discovers and opens the first available
IDS camera, grabs a single frame, converts it to a BGR numpy array, and
saves it as a PNG.

Exit codes:
    0 - Camera detected and test image saved successfully
    1 - Camera not found, import error, or capture failure
"""
from __future__ import annotations

import signal
import sys

TIMEOUT_SECONDS = 10
OUTPUT_PATH = "/tmp/bugsi_rgb_camera_test.png"
FRAME_TIMEOUT_MS = 5_000


def _timeout_handler(signum: int, frame: object) -> None:
    print("[BUGSI] ERROR: Timed out after %d seconds -- aborting." % TIMEOUT_SECONDS)
    sys.exit(1)


def main() -> int:
    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(TIMEOUT_SECONDS)

    print("[BUGSI] Importing ids_peak ...")
    try:
        from ids_peak import ids_peak as peak
        from ids_peak_ipl import ids_peak_ipl as ipl
    except ImportError as exc:
        print("[BUGSI] FAIL: Could not import ids_peak / ids_peak_ipl -- "
              "is the IDS peak SDK installed?")
        print("[BUGSI]       %s" % exc)
        return 1

    try:
        import numpy as np
    except ImportError as exc:
        print("[BUGSI] FAIL: Could not import numpy.")
        print("[BUGSI]       %s" % exc)
        return 1

    try:
        import cv2
    except ImportError as exc:
        print("[BUGSI] FAIL: Could not import cv2 -- is opencv-python installed?")
        print("[BUGSI]       %s" % exc)
        return 1

    device = None
    datastream = None
    node_map_remote = None

    try:
        print("[BUGSI] Initialising ids_peak library ...")
        peak.Library.Initialize()

        print("[BUGSI] Discovering IDS cameras ...")
        device_manager = peak.DeviceManager.Instance()
        device_manager.Update()

        if device_manager.Devices().empty():
            print("[BUGSI] FAIL: No IDS cameras found.")
            print("[BUGSI]       Is the camera connected and the USB driver loaded?")
            return 1

        device_descriptors = device_manager.Devices()
        print("[BUGSI] Found %d device(s)." % device_descriptors.size())

        print("[BUGSI] Opening first available device ...")
        device = device_descriptors[0].OpenDevice(peak.DeviceAccessType_Control)
        node_map_remote = device.RemoteDevice().NodeMaps()[0]

        model = ""
        try:
            model = node_map_remote.FindNode("DeviceModelName").Value()
        except Exception:
            model = "(unknown model)"
        print("[BUGSI] Opened device: %s" % model)

        # Set pixel format
        try:
            for fmt_name in ("BayerRG8", "BGR8", "RGB8", "Mono8"):
                try:
                    node_map_remote.FindNode("PixelFormat").SetCurrentEntry(
                        node_map_remote.FindNode("PixelFormat").FindEntry(fmt_name)
                    )
                    print("[BUGSI] Pixel format set to %s." % fmt_name)
                    break
                except Exception:
                    continue
        except Exception:
            print("[BUGSI] WARN: Could not set pixel format -- using device default.")

        # Prepare datastream
        datastream = device.DataStreams()[0].OpenDataStream()

        payload_size = node_map_remote.FindNode("PayloadSize").Value()
        min_buffers = datastream.NumBuffersAnnouncedMinRequired()
        buffer_count = max(min_buffers, 3)

        for _ in range(buffer_count):
            buf = datastream.AllocAndAnnounceBuffer(payload_size)
            datastream.QueueBuffer(buf)

        # Start acquisition
        print("[BUGSI] Starting acquisition ...")
        datastream.StartAcquisition()
        node_map_remote.FindNode("TLParamsLocked").SetValue(1)
        node_map_remote.FindNode("AcquisitionStart").Execute()
        node_map_remote.FindNode("AcquisitionStart").WaitUntilDone()

        # Grab one frame
        print("[BUGSI] Waiting for frame (timeout %d ms) ..." % FRAME_TIMEOUT_MS)
        buffer = datastream.WaitForFinishedBuffer(FRAME_TIMEOUT_MS)

        raw_image = ipl.Image.CreateFromSizeAndBuffer(
            buffer.PixelFormat(),
            buffer.BasePtr(),
            buffer.Size(),
            buffer.Width(),
            buffer.Height(),
        )
        bgr_image = raw_image.ConvertTo(ipl.PixelFormatName_BGR8)

        np_frame = np.array(bgr_image.get_numpy_3D(), dtype=np.uint8).copy()

        datastream.QueueBuffer(buffer)

        print("[BUGSI] Frame captured: %dx%d" % (np_frame.shape[1], np_frame.shape[0]))

        # Stop acquisition
        print("[BUGSI] Stopping acquisition ...")
        node_map_remote.FindNode("AcquisitionStop").Execute()
        node_map_remote.FindNode("TLParamsLocked").SetValue(0)
        datastream.StopAcquisition(peak.AcquisitionStopMode_Default)

        datastream.Flush(peak.DataStreamFlushMode_DiscardAll)
        for buf in datastream.AnnouncedBuffers():
            datastream.RevokeBuffer(buf)

        # Save PNG
        print("[BUGSI] Saving test frame to %s ..." % OUTPUT_PATH)
        success = cv2.imwrite(OUTPUT_PATH, np_frame)
        if not success:
            print("[BUGSI] FAIL: cv2.imwrite returned False.")
            return 1

        print("[BUGSI] SUCCESS: RGB camera test passed (frame saved).")
        return 0

    except Exception as exc:
        print("[BUGSI] FAIL: %s" % exc)
        return 1

    finally:
        try:
            if datastream is not None:
                try:
                    datastream.StopAcquisition(peak.AcquisitionStopMode_Default)
                except Exception:
                    pass
                try:
                    datastream.Flush(peak.DataStreamFlushMode_DiscardAll)
                except Exception:
                    pass
                for buf in datastream.AnnouncedBuffers():
                    try:
                        datastream.RevokeBuffer(buf)
                    except Exception:
                        pass
        except Exception:
            pass

        if node_map_remote is not None:
            try:
                node_map_remote.FindNode("TLParamsLocked").SetValue(0)
            except Exception:
                pass

        try:
            peak.Library.Close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
