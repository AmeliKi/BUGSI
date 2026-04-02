#!/usr/bin/env python3
"""
BUGSI Hardware Verification: IDS uEye EVS Event Camera (via OpenEB)

Opens the event camera, captures a short burst of events, generates a frame
from the accumulated event histogram, and saves it as a PNG.

Exit codes:
    0 - Camera detected and test image saved successfully
    1 - Camera not found, import error, or capture failure
"""
from __future__ import annotations

import signal
import sys
import time

TIMEOUT_SECONDS = 10
OUTPUT_PATH = "/tmp/bugsi_event_camera_test.png"
CAPTURE_DURATION_US = 500_000  # 500 ms in microseconds (OpenEB uses us)
DELTA_T_US = 50_000  # read events in 50 ms slices


def _timeout_handler(signum: int, frame: object) -> None:
    print("[BUGSI] ERROR: Timed out after %d seconds -- aborting." % TIMEOUT_SECONDS)
    sys.exit(1)


def main() -> int:
    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(TIMEOUT_SECONDS)

    print("[BUGSI] Importing OpenEB (metavision_core) ...")
    try:
        from metavision_core.event_io import EventsIterator
    except ImportError as exc:
        print("[BUGSI] FAIL: Could not import metavision_core.event_io -- "
              "is OpenEB installed?")
        print("[BUGSI]       %s" % exc)
        return 1

    try:
        import cv2
    except ImportError as exc:
        print("[BUGSI] FAIL: Could not import cv2 -- is opencv-python installed?")
        print("[BUGSI]       %s" % exc)
        return 1

    try:
        import numpy as np
    except ImportError as exc:
        print("[BUGSI] FAIL: Could not import numpy.")
        print("[BUGSI]       %s" % exc)
        return 1

    # --- Open camera ----------------------------------------------------------
    print("[BUGSI] Opening event camera (empty string = first available device) ...")
    try:
        iterator = EventsIterator(
            input_path="",
            delta_t=DELTA_T_US,
            mode="delta_t",
        )
    except Exception as exc:
        print("[BUGSI] FAIL: Could not open the event camera.")
        print("[BUGSI]       Is the IDS uEye EVS connected and the driver loaded?")
        print("[BUGSI]       %s" % exc)
        return 1

    # --- Capture events -------------------------------------------------------
    print("[BUGSI] Capturing events for %d ms ..." % (CAPTURE_DURATION_US // 1_000))
    try:
        height, width = iterator.get_size()
    except Exception:
        height, width = 320, 320

    pos_hist = np.zeros((height, width), dtype=np.float64)
    neg_hist = np.zeros((height, width), dtype=np.float64)

    total_events = 0
    accumulated_us = 0
    start_wall = time.monotonic()

    try:
        for events in iterator:
            if events.size == 0:
                accumulated_us += DELTA_T_US
                if accumulated_us >= CAPTURE_DURATION_US:
                    break
                continue

            total_events += events.size

            x = events["x"]
            y = events["y"]
            p = events["p"]

            pos_mask = p == 1
            neg_mask = ~pos_mask

            if pos_mask.any():
                np.add.at(pos_hist, (y[pos_mask], x[pos_mask]), 1)
            if neg_mask.any():
                np.add.at(neg_hist, (y[neg_mask], x[neg_mask]), 1)

            accumulated_us += DELTA_T_US
            if accumulated_us >= CAPTURE_DURATION_US:
                break

            if time.monotonic() - start_wall > TIMEOUT_SECONDS - 2:
                print("[BUGSI] WARN: Wall-clock safety limit reached, stopping capture.")
                break
    except Exception as exc:
        print("[BUGSI] FAIL: Error while reading events: %s" % exc)
        return 1

    print("[BUGSI] Captured %d events in ~%d ms." % (total_events, accumulated_us // 1_000))

    if total_events == 0:
        print("[BUGSI] WARN: Zero events captured. The sensor is connected but "
              "may need motion / light changes to generate events.")
        print("[BUGSI] Saving blank frame anyway (camera connection verified).")

    # --- Generate frame -------------------------------------------------------
    # Blue = positive events, Red = negative events, Green = overlap.
    frame = np.zeros((height, width, 3), dtype=np.uint8)

    if pos_hist.max() > 0:
        frame[:, :, 0] = np.clip(
            pos_hist / pos_hist.max() * 255, 0, 255
        ).astype(np.uint8)
    if neg_hist.max() > 0:
        frame[:, :, 2] = np.clip(
            neg_hist / neg_hist.max() * 255, 0, 255
        ).astype(np.uint8)

    overlap = np.minimum(pos_hist, neg_hist)
    if overlap.max() > 0:
        frame[:, :, 1] = np.clip(
            overlap / overlap.max() * 255, 0, 255
        ).astype(np.uint8)

    # --- Save PNG -------------------------------------------------------------
    print("[BUGSI] Saving test frame to %s ..." % OUTPUT_PATH)
    try:
        success = cv2.imwrite(OUTPUT_PATH, frame)
        if not success:
            print("[BUGSI] FAIL: cv2.imwrite returned False.")
            return 1
    except Exception as exc:
        print("[BUGSI] FAIL: Could not save image: %s" % exc)
        return 1

    print("[BUGSI] SUCCESS: Event camera test passed (%d events, frame saved)." % total_events)
    return 0


if __name__ == "__main__":
    sys.exit(main())
