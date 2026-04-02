"""Async JPEG camera wrappers for the device webserver.

Wraps camera interfaces from the hardware abstraction layer and provides
async JPEG snapshot capture for the web UI.
"""
from __future__ import annotations

import asyncio
import logging
import threading

import cv2

logger = logging.getLogger(__name__)


class WebCamera:
    """Thread-safe camera wrapper that provides JPEG snapshots.

    The underlying camera (ArducamCamera, IDSRGBCamera, or MockCamera) uses
    synchronous calls, so capture runs in a thread executor to avoid blocking
    the async event loop.
    """

    def __init__(self, camera, jpeg_quality: int = 85, stream_width: int = 960):
        self._camera = camera
        self._jpeg_quality = jpeg_quality
        self._stream_width = stream_width
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
            try:
                frame = self._camera.capture()
            except Exception:
                logger.warning("Capture failed, closing camera for re-open on next attempt")
                try:
                    self._camera.close()
                except Exception:
                    pass
                raise
        # Downscale for web preview (detection pipeline uses full-res directly)
        if self._stream_width > 0 and frame.shape[1] > self._stream_width:
            scale = self._stream_width / frame.shape[1]
            new_h = int(frame.shape[0] * scale)
            frame = cv2.resize(frame, (self._stream_width, new_h), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self._jpeg_quality])
        if not ok:
            raise RuntimeError("JPEG encoding failed")
        return buf.tobytes()


class WebEventCamera:
    """Async event camera wrapper that provides JPEG snapshots.

    Wraps an EventCameraInterface. Since capture_event_frame() is already
    async, no executor is needed.
    """

    def __init__(self, event_camera, jpeg_quality: int = 85):
        self._camera = event_camera
        self._jpeg_quality = jpeg_quality
        self._started = False

    async def open(self) -> None:
        if not self._started:
            await self._camera.initialize()
            await self._camera.start_detection()
            self._started = True
            logger.info("WebEventCamera opened")

    async def close(self) -> None:
        if self._started:
            await self._camera.stop_detection()
            await self._camera.shutdown()
            self._started = False
            logger.info("WebEventCamera closed")

    async def capture_jpeg(self) -> bytes:
        """Capture an event visualization frame and encode as JPEG."""
        if not self._started:
            await self.open()
        frame = await self._camera.capture_event_frame()
        ok, buf = cv2.imencode(
            ".jpg", frame,
            [cv2.IMWRITE_JPEG_QUALITY, self._jpeg_quality],
        )
        if not ok:
            raise RuntimeError("JPEG encoding failed")
        return buf.tobytes()
