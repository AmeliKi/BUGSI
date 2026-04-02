from __future__ import annotations

import pytest

from bugsi_daemon.hardware_mock.camera import MockCamera
from bugsi_daemon.hardware_mock.event_camera import MockEventCamera
from bugsi_daemon.web.camera import WebCamera, WebEventCamera


@pytest.fixture
def mock_event_camera():
    return MockEventCamera(frame_width=160, frame_height=120)


@pytest.fixture
def web_event_camera(mock_event_camera):
    return WebEventCamera(mock_event_camera, jpeg_quality=70)


async def test_capture_jpeg_returns_bytes(web_event_camera):
    data = await web_event_camera.capture_jpeg()
    assert isinstance(data, bytes)
    assert len(data) > 0
    # JPEG magic bytes
    assert data[:2] == b"\xff\xd8"


async def test_open_initializes_and_starts_detection(web_event_camera, mock_event_camera):
    assert not mock_event_camera.is_powered()
    assert not mock_event_camera.is_detecting()

    await web_event_camera.open()

    assert mock_event_camera.is_powered()
    assert mock_event_camera.is_detecting()
    assert web_event_camera._started is True


async def test_close_stops_and_shuts_down(web_event_camera, mock_event_camera):
    await web_event_camera.open()
    assert mock_event_camera.is_detecting()

    await web_event_camera.close()

    assert not mock_event_camera.is_powered()
    assert not mock_event_camera.is_detecting()
    assert web_event_camera._started is False


async def test_lazy_open_on_capture(web_event_camera, mock_event_camera):
    assert not mock_event_camera.is_powered()

    # capture_jpeg should auto-open
    data = await web_event_camera.capture_jpeg()

    assert mock_event_camera.is_powered()
    assert mock_event_camera.is_detecting()
    assert isinstance(data, bytes)
    assert len(data) > 0


async def test_close_without_open_is_noop(web_event_camera):
    # Should not raise
    await web_event_camera.close()
    assert web_event_camera._started is False


# --- WebCamera downscale tests ---


def test_webcamera_downscale_produces_smaller_jpeg():
    """stream_width downscales the frame before JPEG encoding."""
    mock = MockCamera(resolution_width=800, resolution_height=600)
    cam_full = WebCamera(mock, jpeg_quality=70, stream_width=0)
    cam_small = WebCamera(mock, jpeg_quality=70, stream_width=320)

    full_bytes = cam_full._capture_jpeg_sync()
    small_bytes = cam_small._capture_jpeg_sync()

    # Both are valid JPEGs
    assert full_bytes[:2] == b"\xff\xd8"
    assert small_bytes[:2] == b"\xff\xd8"
    # Downscaled version should be smaller
    assert len(small_bytes) < len(full_bytes)


def test_webcamera_no_downscale_when_frame_smaller_than_stream_width():
    """If the frame is already smaller than stream_width, no resize happens."""
    mock = MockCamera(resolution_width=320, resolution_height=240)
    cam = WebCamera(mock, jpeg_quality=70, stream_width=960)

    data = cam._capture_jpeg_sync()
    assert data[:2] == b"\xff\xd8"
    assert len(data) > 0


def test_webcamera_stream_width_zero_means_full_res():
    """stream_width=0 disables downscaling."""
    mock = MockCamera(resolution_width=800, resolution_height=600)
    cam = WebCamera(mock, jpeg_quality=70, stream_width=0)

    data = cam._capture_jpeg_sync()
    assert data[:2] == b"\xff\xd8"
    assert len(data) > 0
