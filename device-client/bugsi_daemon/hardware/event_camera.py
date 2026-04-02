"""Prophesee GenX320 event camera driver.

Uses the OpenEB/Metavision SDK for event-based insect detection.
Only works on Raspberry Pi with the Prophesee drivers installed.
On other platforms, initialize() raises NotImplementedError so the
fallback to MockEventCamera is triggered by cli.py.
"""
from __future__ import annotations

import asyncio
import glob
import logging
import os
import time

import numpy as np

from bugsi_daemon.hardware.base import EventCameraInterface, register_event_camera

logger = logging.getLogger(__name__)

_RETRY_BASE_DELAY = 1.0      # Initial retry delay in seconds
_RETRY_MAX_DELAY = 30.0      # Maximum retry delay in seconds
_RETRY_BACKOFF_FACTOR = 2.0  # Exponential backoff multiplier


@register_event_camera("prophesee_genx320")
class PropheseeEventCamera(EventCameraInterface):
    """Prophesee GenX320 event camera via OpenEB/Metavision SDK."""

    @staticmethod
    def _resolve_device_path(configured_path: str) -> str:
        """Resolve the V4L2 device path for the GenX320.

        If *configured_path* is ``"auto"``, scan sysfs for a video device
        whose driver name contains ``genx320``.  Falls back to ``/dev/video0``.
        """
        if configured_path != "auto":
            return configured_path

        for name_file in sorted(glob.glob("/sys/class/video4linux/video*/name")):
            try:
                with open(name_file) as f:
                    name = f.read().strip()
                if "genx320" in name.lower():
                    video_dev = name_file.split("/")[-2]  # e.g. "video0"
                    path = f"/dev/{video_dev}"
                    logger.info("Auto-detected GenX320 at %s (name=%s)", path, name)
                    return path
            except OSError:
                continue

        logger.warning("Could not auto-detect GenX320, falling back to /dev/video0")
        return "/dev/video0"

    DETECTION_COOLDOWN_S = 2.0  # seconds between detection signals/log messages

    def __init__(
        self,
        device_path: str = "auto",
        event_threshold: int = 500,
        detection_window_ms: int = 50,
        min_cluster_area: int = 100,
    ) -> None:
        self._configured_path = device_path
        self._device_path = self._resolve_device_path(device_path)
        self._event_threshold = event_threshold
        self._detection_window_ms = detection_window_ms
        self._min_cluster_area = min_cluster_area
        self._powered = False
        self._detecting = False
        self._device = None
        self._detection_event = asyncio.Event()
        self._detection_task: asyncio.Task | None = None
        self._last_event_frame: np.ndarray | None = None
        self._last_detection_time: float = 0.0

    async def initialize(self) -> None:
        try:
            from metavision_core.event_io import EventsIterator  # noqa: F401
        except ImportError:
            raise NotImplementedError(
                "metavision_core not available — install OpenEB SDK on Raspberry Pi"
            )
        if self._configured_path == "auto":
            self._device_path = self._resolve_device_path("auto")
        if not os.path.exists(self._device_path):
            raise NotImplementedError(
                f"V4L2 device {self._device_path} not found — "
                "check dtoverlay=genx320,cam0 in /boot/firmware/config.txt"
            )
        self._powered = True
        logger.info("PropheseeEventCamera initialized (device=%s)", self._device_path)

    async def power_on(self) -> None:
        await self.initialize()

    async def power_off(self) -> None:
        await self.shutdown()

    def is_powered(self) -> bool:
        return self._powered

    async def start_detection(self) -> None:
        if not self._powered:
            raise RuntimeError("Event camera not powered on")
        self._detecting = True
        self._detection_event.clear()
        self._detection_task = asyncio.create_task(self._detection_loop())
        logger.info("PropheseeEventCamera detection started")

    async def stop_detection(self) -> None:
        self._detecting = False
        if self._detection_task and not self._detection_task.done():
            self._detection_task.cancel()
            try:
                await self._detection_task
            except asyncio.CancelledError:
                pass
        self._detection_task = None
        logger.info("PropheseeEventCamera detection stopped")

    async def wait_for_detection(self, timeout: float | None = None) -> bool:
        if not self._detecting:
            return False
        self._detection_event.clear()
        try:
            await asyncio.wait_for(self._detection_event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    async def capture_event_frame(self) -> np.ndarray:
        if self._last_event_frame is not None:
            return self._last_event_frame
        # Return empty frame if no events accumulated yet
        return np.zeros((480, 640, 3), dtype=np.uint8)

    async def shutdown(self) -> None:
        await self.stop_detection()
        self._powered = False
        self._device = None
        logger.info("PropheseeEventCamera shutdown")

    def is_detecting(self) -> bool:
        return self._detecting

    async def _detection_loop(self) -> None:
        """Background task: read events and trigger detections.

        Re-resolves the device path when configured as ``"auto"`` and retries
        with exponential backoff when the camera cannot be opened (e.g. after
        a USB port change).
        """
        from metavision_core.event_io import EventsIterator

        delay = _RETRY_BASE_DELAY
        try:
            while self._detecting:
                # Re-resolve on each attempt when configured as "auto"
                if self._configured_path == "auto":
                    self._device_path = self._resolve_device_path("auto")

                try:
                    iterator = EventsIterator(
                        self._device_path,
                        delta_t=self._detection_window_ms * 1000,  # microseconds
                    )
                except Exception:
                    logger.warning(
                        "Failed to open event camera at %s, retrying in %.1fs",
                        self._device_path, delay,
                    )
                    await asyncio.sleep(delay)
                    delay = min(delay * _RETRY_BACKOFF_FACTOR, _RETRY_MAX_DELAY)
                    continue

                delay = _RETRY_BASE_DELAY  # reset on success

                try:
                    for events in iterator:
                        if not self._detecting:
                            break

                        # Accumulate events into a frame for visualization
                        frame = np.zeros((480, 640, 3), dtype=np.uint8)
                        if len(events) > 0:
                            x = events["x"]
                            y = events["y"]
                            p = events["p"]
                            valid = (x < 640) & (y < 480)
                            frame[y[valid & (p == 1)], x[valid & (p == 1)]] = [0, 0, 255]
                            frame[y[valid & (p == 0)], x[valid & (p == 0)]] = [255, 0, 0]

                        self._last_event_frame = frame

                        # Detection: threshold on event count with cooldown
                        if len(events) >= self._event_threshold:
                            now = time.monotonic()
                            if now - self._last_detection_time >= self.DETECTION_COOLDOWN_S:
                                self._last_detection_time = now
                                logger.info(
                                    "Insect detection: %d events (threshold=%d)",
                                    len(events),
                                    self._event_threshold,
                                )
                                self._detection_event.set()

                        # Yield to event loop
                        await asyncio.sleep(0)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception(
                        "Event camera read failed at %s, retrying in %.1fs",
                        self._device_path, delay,
                    )
                    await asyncio.sleep(delay)
                    delay = min(delay * _RETRY_BACKOFF_FACTOR, _RETRY_MAX_DELAY)

        except asyncio.CancelledError:
            pass
        finally:
            self._detecting = False
