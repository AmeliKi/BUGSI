"""Async JPEG camera wrapper for the device webserver.

Wraps a CameraInterface from the hardware abstraction layer and provides
thread-safe async JPEG snapshot capture for the web UI.
"""
from __future__ import annotations

import asyncio
import logging
import threading

import cv2

logger = logging.getLogger(__name__)


class WebCamera:
    """Thread-safe camera wrapper that provides JPEG snapshots.

    The underlying camera (ArducamCamera or MockCamera) uses synchronous
    calls, so capture runs in a thread executor to avoid blocking the
    async event loop.
    """

    def __init__(self, camera, jpeg_quality: int = 85):
        self._camera = camera
        self._jpeg_quality = jpeg_quality
        self._lock = threading.Lock()

    def open(self) -> None:
        with self._lock:
            if not self._camera.is_open():
                self._camera.open()
                logger.info("WebCamera opened")

    def close(self) -> None:
        with self._lock:
            if self._camera.is_open():
                self._camera.close()
                logger.info("WebCamera closed")

    async def capture_jpeg(self) -> bytes:
        """Capture a frame and encode as JPEG. Runs in executor to avoid blocking."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._capture_jpeg_sync)

    def _capture_jpeg_sync(self) -> bytes:
        with self._lock:
            if not self._camera.is_open():
                self._camera.open()
            frame = self._camera.capture()
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self._jpeg_quality])
        if not ok:
            raise RuntimeError("JPEG encoding failed")
        return buf.tobytes()
