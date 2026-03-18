"""Tests for the image capture pipeline."""
from __future__ import annotations

import os

import numpy as np
import pytest
import pytest_asyncio

from bugsi_daemon.buffer.store import BufferStore
from bugsi_daemon.config import ConfigManager
from bugsi_daemon.core.image_capture_pipeline import ImageCapturePipeline
from bugsi_daemon.hardware_mock.camera import MockCamera
from bugsi_daemon.hardware_mock.climate import MockClimate
from bugsi_daemon.hardware_mock.event_camera import MockEventCamera


@pytest_asyncio.fixture
async def pipeline(tmp_path, config_manager, buffer_store):
    """Create an image capture pipeline with mock hardware."""
    event_cam = MockEventCamera(
        detection_probability=1.0,
        min_wait_seconds=0.01,
        max_wait_seconds=0.02,
    )
    await event_cam.initialize()

    still_cam = MockCamera(resolution_width=160, resolution_height=120)

    climate = MockClimate()
    # Don't initialize - pipeline should handle power on/off

    save_dir = str(tmp_path / "detections")

    pipeline = ImageCapturePipeline(
        config=config_manager,
        event_camera=event_cam,
        still_camera=still_cam,
        climate=climate,
        buffer=buffer_store,
        save_dir=save_dir,
    )
    return pipeline


@pytest.mark.asyncio
class TestImageCapturePipeline:
    async def test_capture_sequence_saves_files(self, pipeline, tmp_path):
        """A single capture sequence should save images, thumbnail, and metadata."""
        await pipeline._capture_sequence()

        save_dir = str(tmp_path / "detections")
        # Check that files were created
        all_files = []
        for root, dirs, files in os.walk(save_dir):
            all_files.extend(files)

        # Should have: still image, event image, thumbnail, metadata
        assert len(all_files) == 4
        assert any("still" in f for f in all_files)
        assert any("event" in f for f in all_files)
        assert any("thumb" in f for f in all_files)
        assert any("meta" in f for f in all_files)

    async def test_pictures_taken_increments(self, pipeline):
        assert pipeline.pictures_taken == 0
        await pipeline._capture_sequence()
        assert pipeline.pictures_taken == 1
        await pipeline._capture_sequence()
        assert pipeline.pictures_taken == 2

    async def test_capture_pushes_thumbnail_to_buffer(self, pipeline, buffer_store):
        await pipeline._capture_sequence()

        pending = await buffer_store.get_pending_thumbnails(limit=10)
        assert len(pending) == 1

    async def test_still_camera_opened_and_closed_per_capture(self, pipeline):
        """Arducam should only be open during capture, not before/after."""
        still_cam = pipeline._still_camera
        assert not still_cam.is_open()
        await pipeline._capture_sequence()
        assert not still_cam.is_open()

    async def test_climate_powered_on_and_off_during_capture(self, pipeline):
        """Zigbee should be powered on for capture and off after."""
        climate = pipeline._climate
        assert not climate.is_powered()
        await pipeline._capture_sequence()
        assert not climate.is_powered()

    async def test_climate_failure_does_not_block_capture(self, pipeline, buffer_store):
        """If climate reading fails, capture should still succeed."""
        # Make climate unhealthy even when powered
        original_read = pipeline._climate.read

        async def failing_read():
            raise RuntimeError("Sensor error")

        pipeline._climate.read = failing_read

        await pipeline._capture_sequence()
        assert pipeline.pictures_taken == 1

        # Thumbnail should still be saved
        pending = await buffer_store.get_pending_thumbnails(limit=10)
        assert len(pending) == 1

    async def test_metadata_includes_climate_data(self, pipeline, tmp_path):
        """Metadata JSON should include temperature and humidity."""
        import json

        await pipeline._capture_sequence()

        save_dir = str(tmp_path / "detections")
        meta_files = []
        for root, dirs, files in os.walk(save_dir):
            meta_files.extend(
                os.path.join(root, f) for f in files if f.endswith("_meta.json")
            )
        assert len(meta_files) == 1

        with open(meta_files[0]) as f:
            metadata = json.load(f)

        assert "temperature" in metadata
        assert "humidity" in metadata
        assert "timestamp" in metadata
        assert "capture_id" in metadata
        assert "still_image_path" in metadata
        assert "event_image_path" in metadata
