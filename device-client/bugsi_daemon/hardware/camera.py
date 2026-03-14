"""Arducam 64MP camera driver using picamera2.

Only works on Raspberry Pi with picamera2 installed.
On other platforms, open() raises NotImplementedError so the fallback
to MockCamera is triggered by cli.py.
"""
from __future__ import annotations

import logging
import time

from bugsi_daemon.hardware.base import CameraInterface

logger = logging.getLogger(__name__)


class ArducamCamera(CameraInterface):
    """Picamera2 wrapper for Arducam 64MP on Raspberry Pi 5."""

    def __init__(
        self,
        resolution_width: int = 3840,
        resolution_height: int = 2160,
        camera_id: int = 0,
        autofocus_mode: str = "continuous",
    ) -> None:
        self._width = resolution_width
        self._height = resolution_height
        self._camera_id = camera_id
        self._autofocus_mode = autofocus_mode
        self._picam2 = None

    def open(self) -> None:
        if self._picam2 is not None:
            return
        try:
            from picamera2 import Picamera2
        except ImportError:
            raise NotImplementedError(
                "picamera2 not available — install it on Raspberry Pi"
            )

        self._picam2 = Picamera2(camera_num=self._camera_id)
        still_config = self._picam2.create_still_configuration(
            main={"size": (self._width, self._height), "format": "BGR888"},
        )
        self._picam2.configure(still_config)

        if self._autofocus_mode == "continuous":
            try:
                from libcamera import controls
                self._picam2.set_controls({"AfMode": controls.AfModeEnum.Continuous})
            except (ImportError, Exception):
                logger.warning("Could not set continuous autofocus")

        self._picam2.start()
        # Let AE/AWB/AF settle
        time.sleep(1.0)
        logger.info("ArducamCamera opened (%dx%d, camera_id=%d)", self._width, self._height, self._camera_id)

    def close(self) -> None:
        if self._picam2 is not None:
            self._picam2.stop()
            self._picam2.close()
            self._picam2 = None
            logger.info("ArducamCamera closed")

    def capture(self):
        if self._picam2 is None:
            raise RuntimeError("Camera not open. Call open() first.")
        return self._picam2.capture_array("main")

    def is_open(self) -> bool:
        return self._picam2 is not None
