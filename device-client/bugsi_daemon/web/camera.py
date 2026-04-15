"""Async JPEG camera wrappers for the device webserver.

Wraps camera interfaces from the hardware abstraction layer and provides
async JPEG snapshot capture for the web UI.  Includes a background frame
producer that caches JPEG-encoded frames so multiple stream clients share
a single capture pipeline, and a CameraCoordinator that mediates access
between the web stream and the image capture pipeline.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class CameraCoordinator:
    """Mediates all access to a shared still camera hardware instance.

    Both the web stream and the image capture pipeline go through this
    coordinator so that concurrent access is properly serialized and the
    web stream can serve cached frames while the pipeline holds the camera.
    """

    def __init__(self, camera) -> None:
        self._camera = camera
        self._lock = threading.Lock()
        self._last_frame: np.ndarray | None = None

    @property
    def raw_camera(self):
        return self._camera

    def capture_full_res(self) -> np.ndarray:
        """Exclusive capture for the image pipeline (full resolution).

        Opens the camera if needed, captures a frame, and caches it.
        """
        with self._lock:
            if not self._camera.is_open():
                self._camera.open()
            frame = self._camera.capture()
            self._last_frame = frame.copy()
            return frame

    def capture_for_stream(self) -> np.ndarray:
        """Non-blocking capture for the web stream.

        If the lock is held (pipeline capturing), returns the last cached
        frame.  Otherwise acquires the lock and captures a fresh frame.
        """
        acquired = self._lock.acquire(blocking=False)
        if not acquired:
            if self._last_frame is not None:
                return self._last_frame
            # No cached frame; must wait for a real capture
            with self._lock:
                if self._last_frame is not None:
                    return self._last_frame
                if not self._camera.is_open():
                    self._camera.open()
                frame = self._camera.capture()
                self._last_frame = frame.copy()
                return frame
        try:
            if not self._camera.is_open():
                self._camera.open()
            try:
                frame = self._camera.capture()
            except Exception:
                logger.warning("Stream capture failed, closing camera for re-open")
                try:
                    self._camera.close()
                except Exception:
                    pass
                raise
            self._last_frame = frame.copy()
            return frame
        finally:
            self._lock.release()

    def open(self) -> None:
        with self._lock:
            if not self._camera.is_open():
                self._camera.open()

    def close(self) -> None:
        with self._lock:
            if self._camera.is_open():
                self._camera.close()

    @property
    def is_locked(self) -> bool:
        acquired = self._lock.acquire(blocking=False)
        if acquired:
            self._lock.release()
            return False
        return True


class WebCamera:
    """Thread-safe camera wrapper that provides JPEG snapshots.

    Includes a background frame producer that continuously captures and
    JPEG-encodes frames so stream clients read from a cache instead of
    each triggering their own hardware capture.
    """

    def __init__(
        self,
        camera,
        jpeg_quality: int = 85,
        stream_width: int = 960,
        coordinator: CameraCoordinator | None = None,
    ):
        self._camera = camera
        self._jpeg_quality = jpeg_quality
        self._stream_jpeg_quality = max(1, min(jpeg_quality, 65))
        self._stream_width = stream_width
        self._lock = threading.Lock()
        self._coordinator = coordinator

        # Background producer state
        self._cached_jpeg: bytes | None = None
        self._frame_ready = asyncio.Event()
        self._stream_clients: int = 0
        self._producer_task: asyncio.Task | None = None
        self._producing = False

    def open(self) -> None:
        if self._coordinator is not None:
            self._coordinator.open()
        else:
            with self._lock:
                if not self._camera.is_open():
                    self._camera.open()
                    logger.info("WebCamera opened")

    def close(self) -> None:
        if self._coordinator is not None:
            self._coordinator.close()
        else:
            with self._lock:
                if self._camera.is_open():
                    self._camera.close()
                    logger.info("WebCamera closed")

    async def capture_jpeg(self) -> bytes:
        """Capture a fresh frame and encode as JPEG (for snapshots)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._capture_jpeg_sync)

    def _capture_jpeg_sync(self) -> bytes:
        if self._coordinator is not None:
            frame = self._coordinator.capture_for_stream()
        else:
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
        return self._encode_frame(frame, self._jpeg_quality)

    def _capture_stream_jpeg_sync(self) -> bytes:
        """Capture and encode with lower quality for streaming."""
        if self._coordinator is not None:
            frame = self._coordinator.capture_for_stream()
        else:
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
        return self._encode_frame(frame, self._stream_jpeg_quality)

    def _encode_frame(self, frame: np.ndarray, quality: int) -> bytes:
        """Downscale and JPEG-encode a frame.

        Uses a two-stage downscale for large images: a fast numpy stride
        to rough-downscale by an integer factor, followed by a small
        cv2.resize for the final dimensions.  This is much faster than a
        single INTER_AREA resize from e.g. 5136x3856 to 960px.
        """
        if self._stream_width > 0 and frame.shape[1] > self._stream_width:
            # Fast rough downscale via numpy striding (nearly free)
            factor = max(1, frame.shape[1] // (self._stream_width * 2))
            if factor > 1:
                frame = frame[::factor, ::factor].copy()
            # Fine resize to exact target dimensions
            scale = self._stream_width / frame.shape[1]
            new_h = int(frame.shape[0] * scale)
            frame = cv2.resize(frame, (self._stream_width, new_h),
                               interpolation=cv2.INTER_LINEAR)
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if not ok:
            raise RuntimeError("JPEG encoding failed")
        return buf.tobytes()

    # --- Background frame producer ---

    async def notify_stream_start(self, fps: float) -> None:
        """Called when a new stream client connects."""
        self._stream_clients += 1
        if self._producer_task is None or self._producer_task.done():
            self._producing = True
            self._producer_task = asyncio.create_task(self._produce_loop(fps))

    async def notify_stream_stop(self) -> None:
        """Called when a stream client disconnects."""
        self._stream_clients = max(0, self._stream_clients - 1)
        if self._stream_clients == 0:
            await self._stop_producing()

    async def _stop_producing(self) -> None:
        self._producing = False
        if self._producer_task is not None and not self._producer_task.done():
            self._producer_task.cancel()
            try:
                await self._producer_task
            except asyncio.CancelledError:
                pass
            self._producer_task = None

    async def _produce_loop(self, fps: float) -> None:
        """Continuously capture frames and cache as JPEG."""
        interval = 1.0 / max(fps, 1)
        loop = asyncio.get_event_loop()
        logger.info("WebCamera producer started (target %.1f fps)", fps)
        try:
            while self._producing:
                cycle_start = time.monotonic()
                try:
                    jpeg_bytes = await loop.run_in_executor(
                        None, self._capture_stream_jpeg_sync,
                    )
                    self._cached_jpeg = jpeg_bytes
                    self._frame_ready.set()
                    self._frame_ready.clear()
                except Exception:
                    logger.warning("Producer capture failed", exc_info=True)
                    await asyncio.sleep(0.5)
                    continue
                elapsed = time.monotonic() - cycle_start
                remaining = interval - elapsed
                if remaining > 0:
                    await asyncio.sleep(remaining)
        except asyncio.CancelledError:
            pass
        finally:
            logger.info("WebCamera producer stopped")

    async def get_cached_jpeg(self) -> bytes:
        """Return the latest cached frame, or capture one if no cache exists."""
        if self._cached_jpeg is not None:
            return self._cached_jpeg
        return await self.capture_jpeg()

    async def stop_producer(self) -> None:
        """Force-stop the background producer (for shutdown)."""
        await self._stop_producing()


class WebEventCamera:
    """Async event camera wrapper that provides JPEG snapshots.

    Wraps an EventCameraInterface. Includes a background producer that
    caches JPEG-encoded event frames to avoid redundant encoding.
    """

    def __init__(self, event_camera, jpeg_quality: int = 85):
        self._camera = event_camera
        self._jpeg_quality = jpeg_quality
        self._stream_jpeg_quality = max(1, min(jpeg_quality, 65))
        self._started = False

        # Background producer state
        self._cached_jpeg: bytes | None = None
        self._frame_ready = asyncio.Event()
        self._stream_clients: int = 0
        self._producer_task: asyncio.Task | None = None
        self._producing = False

    async def open(self) -> None:
        if not self._started:
            await self._camera.initialize()
            await self._camera.start_detection()
            self._started = True
            logger.info("WebEventCamera opened")

    async def close(self) -> None:
        await self._stop_producing()
        if self._started:
            await self._camera.stop_detection()
            await self._camera.shutdown()
            self._started = False
            logger.info("WebEventCamera closed")

    async def capture_jpeg(self) -> bytes:
        """Capture an event visualization frame and encode as JPEG (for snapshots)."""
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

    async def _capture_stream_jpeg(self) -> bytes:
        """Capture event frame with lower quality for streaming."""
        if not self._started:
            await self.open()
        frame = await self._camera.capture_event_frame()
        ok, buf = cv2.imencode(
            ".jpg", frame,
            [cv2.IMWRITE_JPEG_QUALITY, self._stream_jpeg_quality],
        )
        if not ok:
            raise RuntimeError("JPEG encoding failed")
        return buf.tobytes()

    # --- Background frame producer ---

    async def notify_stream_start(self, fps: float) -> None:
        """Called when a new stream client connects."""
        self._stream_clients += 1
        if self._producer_task is None or self._producer_task.done():
            self._producing = True
            self._producer_task = asyncio.create_task(self._produce_loop(fps))

    async def notify_stream_stop(self) -> None:
        """Called when a stream client disconnects."""
        self._stream_clients = max(0, self._stream_clients - 1)
        if self._stream_clients == 0:
            await self._stop_producing()

    async def _stop_producing(self) -> None:
        self._producing = False
        if self._producer_task is not None and not self._producer_task.done():
            self._producer_task.cancel()
            try:
                await self._producer_task
            except asyncio.CancelledError:
                pass
            self._producer_task = None

    async def _produce_loop(self, fps: float) -> None:
        """Continuously capture event frames and cache as JPEG."""
        interval = 1.0 / max(fps, 1)
        logger.info("WebEventCamera producer started (target %.1f fps)", fps)
        try:
            while self._producing:
                cycle_start = time.monotonic()
                try:
                    jpeg_bytes = await self._capture_stream_jpeg()
                    self._cached_jpeg = jpeg_bytes
                    self._frame_ready.set()
                    self._frame_ready.clear()
                except Exception:
                    logger.warning("Event producer capture failed", exc_info=True)
                    await asyncio.sleep(0.5)
                    continue
                elapsed = time.monotonic() - cycle_start
                remaining = interval - elapsed
                if remaining > 0:
                    await asyncio.sleep(remaining)
        except asyncio.CancelledError:
            pass
        finally:
            logger.info("WebEventCamera producer stopped")

    async def get_cached_jpeg(self) -> bytes:
        """Return the latest cached frame, or capture one if no cache exists."""
        if self._cached_jpeg is not None:
            return self._cached_jpeg
        return await self.capture_jpeg()

    async def stop_producer(self) -> None:
        """Force-stop the background producer (for shutdown)."""
        await self._stop_producing()
