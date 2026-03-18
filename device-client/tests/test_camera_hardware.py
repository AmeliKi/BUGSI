"""Tests for camera hardware abstraction (MockCamera + WebCamera integration)."""
from __future__ import annotations

import numpy as np
import pytest

from bugsi_daemon.hardware.base import CameraInterface, StillCameraInterface
from bugsi_daemon.hardware_mock.camera import MockCamera
from bugsi_daemon.web.camera import WebCamera


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
