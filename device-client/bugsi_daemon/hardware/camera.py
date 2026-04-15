"""Arducam 64MP camera driver using picamera2.

Only works on Raspberry Pi with picamera2 installed.
On other platforms, open() raises NotImplementedError so the fallback
to MockCamera is triggered by cli.py.
"""
from __future__ import annotations

import logging
import time

from bugsi_daemon.hardware.base import StillCameraInterface, register_still_camera

logger = logging.getLogger(__name__)


@register_still_camera("arducam_64mp")
class ArducamCamera(StillCameraInterface):
    """Picamera2 wrapper for Arducam 64MP on Raspberry Pi 5."""

    def __init__(
        self,
        resolution_width: int = 3840,
        resolution_height: int = 2160,
        camera_id: int = 1,
        autofocus_mode: str = "continuous",
        exposure_us: float = 0,
        gain_db: float = 0.0,
        **kwargs,
    ) -> None:
        self._width = resolution_width
        self._height = resolution_height
        self._camera_id = camera_id
        self._autofocus_mode = autofocus_mode
        self._exposure_us = exposure_us
        self._gain_db = gain_db
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

        camera_num = self._resolve_camera_num(Picamera2)
        self._picam2 = Picamera2(camera_num=camera_num)
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

        # Apply manual exposure/gain if configured (0 = auto)
        controls_to_set = {}
        if self._exposure_us > 0:
            controls_to_set["ExposureTime"] = int(self._exposure_us)
            controls_to_set["AeEnable"] = False
            logger.info("Exposure set to %d us (manual)", int(self._exposure_us))
        if self._gain_db > 0:
            controls_to_set["AnalogueGain"] = self._gain_db
            if "AeEnable" not in controls_to_set:
                controls_to_set["AeEnable"] = False
            logger.info("Gain set to %.1f (manual)", self._gain_db)
        if controls_to_set:
            self._picam2.set_controls(controls_to_set)

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

    def _resolve_camera_num(self, picamera2_cls) -> int:
        """Find the correct libcamera index for the Arducam.

        The configured camera_id may be wrong if the Prophesee event camera
        (USB/CSI) doesn't register as a libcamera device. We try the
        configured ID first, then fall back to scanning available cameras.
        """
        cameras = picamera2_cls.global_camera_info()
        if not cameras:
            raise RuntimeError(
                "No libcamera cameras found. If using Arducam 64MP on Pi 5, "
                "make sure the IPA tuning file is installed: "
                "ls /usr/share/libcamera/ipa/rpi/pisp/arducam_64mp.json — "
                "see https://docs.arducam.com for the install script."
            )

        # Configured ID is valid
        if self._camera_id < len(cameras):
            return cameras[self._camera_id]["Num"]

        # Fall back: use the first (and likely only) available camera
        logger.warning(
            "camera_id=%d out of range (%d cameras available), using camera 0",
            self._camera_id,
            len(cameras),
        )
        return cameras[0]["Num"]
