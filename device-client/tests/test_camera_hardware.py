"""Tests for camera hardware abstraction (MockCamera + WebCamera + CameraCoordinator)."""
from __future__ import annotations
from unittest.mock import MagicMock

import numpy as np
import pytest

from bugsi_daemon.hardware.base import CameraInterface, StillCameraInterface
from bugsi_daemon.hardware_mock.camera import MockCamera
from bugsi_daemon.web.camera import CameraCoordinator, WebCamera


class TestMockCamera:
    def test_open_close(self):
        camera = MockCamera()
        assert not camera.is_open()
        camera.open()
        assert camera.is_open()
        camera.close()
        assert not camera.is_open()

    def test_capture_returns_bgr_array(self):
        camera = MockCamera()
        camera.open()
        frame = camera.capture()
        assert isinstance(frame, np.ndarray)
        assert frame.ndim == 3
        assert frame.shape[2] == 3  # BGR channels
        camera.close()

    def test_capture_when_closed_raises(self):
        camera = MockCamera()
        with pytest.raises(RuntimeError):
            camera.capture()

    def test_capture_deterministic(self):
        cam1 = MockCamera()
        cam2 = MockCamera()
        cam1.open()
        cam2.open()
        assert np.array_equal(cam1.capture(), cam2.capture())
        cam1.close()
        cam2.close()

    def test_custom_resolution(self):
        camera = MockCamera(resolution_width=320, resolution_height=240)
        camera.open()
        frame = camera.capture()
        assert frame.shape == (240, 320, 3)
        camera.close()

    def test_default_resolution(self):
        camera = MockCamera()
        camera.open()
        frame = camera.capture()
        assert frame.shape == (480, 640, 3)
        camera.close()

    def test_implements_camera_interface(self):
        assert isinstance(MockCamera(), CameraInterface)

    def test_frames_differ(self):
        camera = MockCamera()
        camera.open()
        f1 = camera.capture()
        f2 = camera.capture()
        # Different frame counts mean different seeds, so frames may differ
        # (but could be identical if both have 0 insects — just verify no crash)
        assert f1.shape == f2.shape
        camera.close()


class TestCameraCoordinator:
    def test_capture_full_res(self):
        camera = MockCamera(resolution_width=160, resolution_height=120)
        coordinator = CameraCoordinator(camera)
        frame = coordinator.capture_full_res()
        assert isinstance(frame, np.ndarray)
        assert frame.shape == (120, 160, 3)

    def test_capture_for_stream(self):
        camera = MockCamera(resolution_width=160, resolution_height=120)
        coordinator = CameraCoordinator(camera)
        frame = coordinator.capture_for_stream()
        assert isinstance(frame, np.ndarray)
        assert frame.shape == (120, 160, 3)

    def test_caches_last_frame(self):
        camera = MockCamera(resolution_width=160, resolution_height=120)
        coordinator = CameraCoordinator(camera)
        frame1 = coordinator.capture_full_res()
        # The internal cache should now be set
        assert coordinator._last_frame is not None
        assert np.array_equal(coordinator._last_frame, frame1)

    def test_open_close(self):
        camera = MockCamera()
        coordinator = CameraCoordinator(camera)
        coordinator.open()
        assert camera.is_open()
        coordinator.close()
        assert not camera.is_open()

    def test_raw_camera_property(self):
        camera = MockCamera()
        coordinator = CameraCoordinator(camera)
        assert coordinator.raw_camera is camera

    def test_stream_returns_cached_when_locked(self):
        """When the lock is held (simulating pipeline capture), stream returns cached frame."""
        camera = MockCamera(resolution_width=160, resolution_height=120)
        coordinator = CameraCoordinator(camera)
        # Prime the cache
        frame1 = coordinator.capture_full_res()
        # Acquire the lock externally to simulate pipeline holding it
        coordinator._lock.acquire()
        try:
            frame2 = coordinator.capture_for_stream()
            # Should return the cached frame
            assert np.array_equal(frame2, frame1)
        finally:
            coordinator._lock.release()


class TestWebCameraWithMock:
    async def test_capture_jpeg_returns_bytes(self):
        camera = MockCamera(resolution_width=160, resolution_height=120)
        web_cam = WebCamera(camera, jpeg_quality=70)
        data = await web_cam.capture_jpeg()
        assert isinstance(data, bytes)
        assert len(data) > 0
        # JPEG magic bytes
        assert data[:2] == b"\xff\xd8"
        web_cam.close()

    async def test_open_close(self):
        camera = MockCamera()
        web_cam = WebCamera(camera, jpeg_quality=85)
        web_cam.open()
        assert camera.is_open()
        web_cam.close()
        assert not camera.is_open()

    async def test_lazy_open_on_capture(self):
        camera = MockCamera()
        web_cam = WebCamera(camera, jpeg_quality=85)
        assert not camera.is_open()
        # capture_jpeg should auto-open
        await web_cam.capture_jpeg()
        assert camera.is_open()
        web_cam.close()

    async def test_closes_camera_on_capture_failure(self):
        """After a capture failure, the camera is closed so next call re-opens."""
        mock_cam = MagicMock()
        mock_cam.is_open.return_value = True
        mock_cam.capture.side_effect = RuntimeError("USB disconnected")

        web_cam = WebCamera(mock_cam, jpeg_quality=85)
        with pytest.raises(RuntimeError, match="USB disconnected"):
            await web_cam.capture_jpeg()

        mock_cam.close.assert_called_once()

    async def test_recovers_after_capture_failure(self):
        """After a failure closes the camera, the next capture re-opens and succeeds."""
        mock_cam = MagicMock()
        call_count = 0

        def capture_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("USB disconnected")
            return np.zeros((120, 160, 3), dtype=np.uint8)

        def is_open_side_effect():
            # After close() was called, report not open
            if mock_cam.close.called and call_count <= 1:
                return False
            return call_count > 1 or not mock_cam.close.called

        mock_cam.capture.side_effect = capture_side_effect
        mock_cam.is_open.side_effect = is_open_side_effect

        web_cam = WebCamera(mock_cam, jpeg_quality=85)

        # First call fails
        with pytest.raises(RuntimeError):
            await web_cam.capture_jpeg()

        # Reset is_open to return False (camera was closed)
        mock_cam.is_open.side_effect = None
        mock_cam.is_open.return_value = False

        # Second call should re-open and succeed
        mock_cam.capture.side_effect = lambda: np.zeros((120, 160, 3), dtype=np.uint8)
        data = await web_cam.capture_jpeg()
        assert isinstance(data, bytes)
        # open() should have been called for the re-open
        mock_cam.open.assert_called()

    async def test_with_coordinator(self):
        """WebCamera with a CameraCoordinator uses it for captures."""
        camera = MockCamera(resolution_width=160, resolution_height=120)
        coordinator = CameraCoordinator(camera)
        web_cam = WebCamera(camera, jpeg_quality=70, coordinator=coordinator)
        data = await web_cam.capture_jpeg()
        assert isinstance(data, bytes)
        assert data[:2] == b"\xff\xd8"

    async def test_stream_jpeg_quality_lower(self):
        """Stream JPEG quality should be capped at 65."""
        camera = MockCamera(resolution_width=160, resolution_height=120)
        web_cam = WebCamera(camera, jpeg_quality=85)
        assert web_cam._stream_jpeg_quality == 65

    async def test_stream_jpeg_quality_kept_if_lower(self):
        """If original quality < 65, stream quality matches it."""
        camera = MockCamera(resolution_width=160, resolution_height=120)
        web_cam = WebCamera(camera, jpeg_quality=50)
        assert web_cam._stream_jpeg_quality == 50


class TestWebCameraProducer:
    async def test_notify_start_stop(self):
        """Producer starts on first stream client, stops on last disconnect."""
        camera = MockCamera(resolution_width=160, resolution_height=120)
        web_cam = WebCamera(camera, jpeg_quality=70)

        await web_cam.notify_stream_start(fps=10)
        assert web_cam._producing is True
        assert web_cam._producer_task is not None
        assert not web_cam._producer_task.done()

        # Let producer run one cycle
        await asyncio.sleep(0.2)
        assert web_cam._cached_jpeg is not None

        await web_cam.notify_stream_stop()
        assert web_cam._producing is False

    async def test_get_cached_jpeg_before_producer(self):
        """get_cached_jpeg falls back to direct capture when no cache."""
        camera = MockCamera(resolution_width=160, resolution_height=120)
        web_cam = WebCamera(camera, jpeg_quality=70)

        data = await web_cam.get_cached_jpeg()
        assert isinstance(data, bytes)
        assert data[:2] == b"\xff\xd8"

    async def test_multiple_clients_single_producer(self):
        """Multiple stream start calls share one producer."""
        camera = MockCamera(resolution_width=160, resolution_height=120)
        web_cam = WebCamera(camera, jpeg_quality=70)

        await web_cam.notify_stream_start(fps=10)
        task1 = web_cam._producer_task

        await web_cam.notify_stream_start(fps=10)
        task2 = web_cam._producer_task

        # Same task, not a new one
        assert task1 is task2
        assert web_cam._stream_clients == 2

        # First stop shouldn't kill producer
        await web_cam.notify_stream_stop()
        assert web_cam._producing is True

        # Second stop should
        await web_cam.notify_stream_stop()
        assert web_cam._producing is False


import asyncio  # noqa: E402 (needed for tests above)
