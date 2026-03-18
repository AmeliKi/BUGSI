"""Mock event camera for development and testing without hardware."""
from __future__ import annotations

import asyncio
import logging
import random

import numpy as np

from bugsi_daemon.hardware.base import EventCameraInterface, register_event_camera

logger = logging.getLogger(__name__)


@register_event_camera("mock")
class MockEventCamera(EventCameraInterface):
    """Simulates an event-based camera with random insect detections."""

    def __init__(
        self,
        detection_probability: float = 0.3,
        min_wait_seconds: float = 2.0,
        max_wait_seconds: float = 10.0,
        frame_width: int = 640,
        frame_height: int = 480,
        **kwargs,  # Accept and ignore hardware-specific config (device_path, etc.)
    ) -> None:
        self._detection_probability = detection_probability
        self._min_wait = min_wait_seconds
        self._max_wait = max_wait_seconds
        self._frame_width = frame_width
        self._frame_height = frame_height
        self._powered = False
        self._detecting = False

    async def initialize(self) -> None:
        self._powered = True
        logger.info("MockEventCamera initialized")

    async def power_on(self) -> None:
        self._powered = True
        logger.info("MockEventCamera powered on")

    async def power_off(self) -> None:
        self._detecting = False
        self._powered = False
        logger.info("MockEventCamera powered off")

    def is_powered(self) -> bool:
        return self._powered

    async def start_detection(self) -> None:
        if not self._powered:
            raise RuntimeError("Event camera not powered on")
        self._detecting = True
        logger.info("MockEventCamera detection started")

    async def stop_detection(self) -> None:
        self._detecting = False
        logger.info("MockEventCamera detection stopped")

    async def wait_for_detection(self, timeout: float | None = None) -> bool:
        if not self._detecting:
            return False

        wait = random.uniform(self._min_wait, self._max_wait)
        if timeout is not None:
            wait = min(wait, timeout)

        await asyncio.sleep(wait)

        if not self._detecting:
            return False

        return random.random() < self._detection_probability

    async def capture_event_frame(self) -> np.ndarray:
        """Generate a synthetic event visualization frame."""
        frame = np.zeros((self._frame_height, self._frame_width, 3), dtype=np.uint8)
        # Simulate event clusters as bright spots on dark background
        n_events = random.randint(50, 300)
        for _ in range(n_events):
            x = random.randint(0, self._frame_width - 1)
            y = random.randint(0, self._frame_height - 1)
            polarity = random.choice([0, 1])
            if polarity:
                frame[y, x] = [0, 0, 255]  # Red for positive events
            else:
                frame[y, x] = [255, 0, 0]  # Blue for negative events
        return frame

    async def shutdown(self) -> None:
        self._detecting = False
        self._powered = False
        logger.info("MockEventCamera shutdown")

    def is_detecting(self) -> bool:
        return self._detecting
