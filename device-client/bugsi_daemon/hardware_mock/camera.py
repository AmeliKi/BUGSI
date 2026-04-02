"""Mock camera for development and testing without hardware."""
from __future__ import annotations

import logging

import cv2
import numpy as np

from bugsi_daemon.hardware.base import StillCameraInterface, register_still_camera

logger = logging.getLogger(__name__)


@register_still_camera("mock")
class MockCamera(StillCameraInterface):
    """Generates synthetic frames with random fake insects."""

    def __init__(
        self,
        resolution_width: int = 640,
        resolution_height: int = 480,
        camera_id: int = 0,
        autofocus_mode: str = "continuous",
        exposure_us: float = 0,
        gain_db: float = 0.0,
        **kwargs,
    ) -> None:
        self._width = resolution_width
        self._height = resolution_height
        self._open = False
        self._frame_count = 0

    def open(self) -> None:
        self._open = True
        logger.info("MockCamera opened (%dx%d)", self._width, self._height)

    def close(self) -> None:
        self._open = False

    def capture(self):
        if not self._open:
            raise RuntimeError("Mock camera not open.")
        # Light background with random synthetic "insects"
        frame = np.full((self._height, self._width, 3), 230, dtype=np.uint8)
        rng = np.random.default_rng(seed=self._frame_count)
        n_insects = rng.integers(0, 4)
        for _ in range(n_insects):
            cx = rng.integers(100, max(self._width - 100, 101))
            cy = rng.integers(100, max(self._height - 100, 101))
            axes = (rng.integers(10, 60), rng.integers(8, 40))
            color = (
                int(rng.integers(0, 180)),
                int(rng.integers(40, 200)),
                int(rng.integers(20, 180)),
            )
            cv2.ellipse(frame, (int(cx), int(cy)), axes, float(rng.integers(0, 360)), 0, 360, color, -1)
        self._frame_count += 1
        return frame

    def is_open(self) -> bool:
        return self._open
