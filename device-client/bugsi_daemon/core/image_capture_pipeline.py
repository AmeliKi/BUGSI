"""Image capture pipeline: event camera detection → still camera capture → save.

Orchestrates the Prophesee event camera for insect detection triggering
the Arducam 64MP for high-resolution image capture, with Zigbee climate
data recorded alongside each image.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone

import cv2
import numpy as np

from bugsi_daemon.buffer.store import BufferStore
from bugsi_daemon.config import ConfigManager
from bugsi_daemon.hardware.base import (
    EventCameraInterface,
    HardwareSensor,
    PowerControllable,
    StillCameraInterface,
)

logger = logging.getLogger(__name__)


class ImageCapturePipeline:
    """Orchestrates event-camera-triggered image capture with sensor data."""

    def __init__(
        self,
        config: ConfigManager,
        event_camera: EventCameraInterface,
        still_camera: StillCameraInterface,
        climate: HardwareSensor,
        buffer: BufferStore,
        save_dir: str,
        coordinator=None,
    ) -> None:
        self._config = config
        self._event_camera = event_camera
        self._still_camera = still_camera
        self._climate = climate
        self._buffer = buffer
        self._save_dir = save_dir
        self._coordinator = coordinator
        self._running = False
        self._pictures_taken = 0
        os.makedirs(save_dir, exist_ok=True)

    @property
    def pictures_taken(self) -> int:
        return self._pictures_taken

    async def run(self) -> None:
        """Main detection loop. Runs until stopped."""
        self._running = True
        await self._event_camera.start_detection()
        logger.info("Image capture pipeline started")

        try:
            while self._running:
                detected = await self._event_camera.wait_for_detection(timeout=60.0)

                if not detected or not self._running:
                    continue

                try:
                    await self._capture_sequence()
                except Exception:
                    logger.exception("Capture sequence failed")

                # Cooldown: stop detection, wait, restart
                cooldown = self._config.get("image_capture.cooldown_seconds", 10)
                if cooldown > 0 and self._running:
                    await self._event_camera.stop_detection()
                    await asyncio.sleep(cooldown)
                    if self._running:
                        await self._event_camera.start_detection()
        except asyncio.CancelledError:
            pass
        finally:
            await self._event_camera.stop_detection()

    async def _capture_sequence(self) -> None:
        """Capture images + climate data on detection."""
        timestamp = datetime.now(timezone.utc)
        capture_id = uuid.uuid4().hex[:8]

        # 1. Power on Zigbee FIRST (start warming up while we capture images)
        climate_powered = False
        if isinstance(self._climate, PowerControllable):
            try:
                await self._climate.power_on()
                climate_powered = True
            except Exception:
                logger.warning("Failed to power on Zigbee for capture")

        try:
            # 2. Capture from still camera (open → capture → close)
            still_frame = self._capture_still()

            # 3. Capture event frame from event camera
            event_frame = await self._event_camera.capture_event_frame()

            # 4. Save both full-resolution images
            still_path = self._save_image(still_frame, timestamp, capture_id, "still")
            event_path = self._save_image(event_frame, timestamp, capture_id, "event")

            # 5. Wait for Zigbee sensor data to arrive
            warmup = self._config.get("image_capture.zigbee_warmup_seconds", 5)
            await asyncio.sleep(warmup)

            # 6. Read climate data
            climate_data = {}
            try:
                if self._climate.is_healthy():
                    climate_data = await self._climate.read()
            except Exception:
                logger.warning("Failed to read climate during capture")

            # 7. Generate and save thumbnail
            thumbnail_path = self._save_thumbnail(still_frame, timestamp, capture_id)

            # 8. Save metadata JSON
            metadata = {
                "capture_id": capture_id,
                "timestamp": timestamp.isoformat(),
                "temperature": climate_data.get("temperature"),
                "humidity": climate_data.get("humidity"),
                "still_image_path": still_path,
                "event_image_path": event_path,
                "thumbnail_path": thumbnail_path,
            }
            self._save_metadata(metadata, timestamp, capture_id)

            # 9. Push thumbnail to buffer for upload
            await self._buffer.push_thumbnail(thumbnail_path, timestamp.isoformat())

            self._pictures_taken += 1
            logger.info(
                "Captured image #%d (id=%s): temp=%s, humidity=%s",
                self._pictures_taken,
                capture_id,
                climate_data.get("temperature"),
                climate_data.get("humidity"),
            )

        finally:
            # 10. Power off Zigbee
            if climate_powered and isinstance(self._climate, PowerControllable):
                try:
                    await self._climate.power_off()
                except Exception:
                    logger.warning("Failed to power off Zigbee after capture")

    def _capture_still(self) -> np.ndarray:
        """Open still camera, capture one frame, close immediately.

        When a CameraCoordinator is available, uses it for thread-safe
        access shared with the web stream.  Otherwise retries once on
        failure to handle USB re-enumeration.
        """
        if self._coordinator is not None:
            return self._coordinator.capture_full_res()

        for attempt in range(2):
            self._still_camera.open()
            try:
                frame = self._still_camera.capture()
                self._still_camera.close()
                return frame
            except Exception:
                logger.warning("Still capture attempt %d failed, re-opening camera", attempt + 1)
                try:
                    self._still_camera.close()
                except Exception:
                    pass
                if attempt == 0:
                    continue
                raise

    def _save_image(
        self,
        frame: np.ndarray,
        timestamp: datetime,
        capture_id: str,
        kind: str,
    ) -> str:
        """Save a full-resolution image to disk."""
        date_dir = timestamp.strftime("%Y-%m-%d")
        dir_path = os.path.join(self._save_dir, date_dir)
        os.makedirs(dir_path, exist_ok=True)

        filename = f"{timestamp.strftime('%H%M%S')}_{capture_id}_{kind}.jpg"
        filepath = os.path.join(dir_path, filename)

        quality = self._config.get("still_camera.jpeg_quality", 85)
        cv2.imwrite(filepath, frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return filepath

    def _save_thumbnail(
        self,
        frame: np.ndarray,
        timestamp: datetime,
        capture_id: str,
    ) -> str:
        """Generate and save a thumbnail for upload."""
        thumb_w = self._config.get("image_capture.thumbnail_width", 480)
        thumb_h = self._config.get("image_capture.thumbnail_height", 360)
        thumbnail = cv2.resize(frame, (thumb_w, thumb_h))

        date_dir = timestamp.strftime("%Y-%m-%d")
        dir_path = os.path.join(self._save_dir, date_dir, "thumbnails")
        os.makedirs(dir_path, exist_ok=True)

        filename = f"{timestamp.strftime('%H%M%S')}_{capture_id}_thumb.jpg"
        filepath = os.path.join(dir_path, filename)

        cv2.imwrite(filepath, thumbnail, [cv2.IMWRITE_JPEG_QUALITY, 70])
        return filepath

    def _save_metadata(
        self,
        metadata: dict,
        timestamp: datetime,
        capture_id: str,
    ) -> None:
        """Save capture metadata as JSON alongside images."""
        date_dir = timestamp.strftime("%Y-%m-%d")
        dir_path = os.path.join(self._save_dir, date_dir)
        os.makedirs(dir_path, exist_ok=True)

        filename = f"{timestamp.strftime('%H%M%S')}_{capture_id}_meta.json"
        filepath = os.path.join(dir_path, filename)

        with open(filepath, "w") as f:
            json.dump(metadata, f, indent=2)

    async def stop(self) -> None:
        """Signal the pipeline to stop."""
        self._running = False
        await self._event_camera.stop_detection()
