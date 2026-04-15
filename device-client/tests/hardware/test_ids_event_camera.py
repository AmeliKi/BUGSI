from __future__ import annotations

import pytest

from bugsi_daemon.hardware.base import EVENT_CAMERA_REGISTRY, EventCameraInterface


def test_ids_evs_registered_in_registry():
    import bugsi_daemon.hardware.ids_event_camera  # noqa: F401
    assert "ids_evs" in EVENT_CAMERA_REGISTRY


def test_resolve_device_path_auto_returns_empty_string():
    from bugsi_daemon.hardware.ids_event_camera import IDSEventCamera
    assert IDSEventCamera._resolve_device_path("auto") == ""


def test_resolve_device_path_explicit_passthrough():
    from bugsi_daemon.hardware.ids_event_camera import IDSEventCamera
    assert IDSEventCamera._resolve_device_path("/dev/video2") == "/dev/video2"


def test_constructor_accepts_config_params():
    from bugsi_daemon.hardware.ids_event_camera import IDSEventCamera
    cam = IDSEventCamera(
        device_path="auto",
        event_threshold=300,
        detection_window_ms=100,
        min_cluster_area=50,
    )
    assert cam._device_path == ""
    assert cam._event_threshold == 300


def test_constructor_stores_configured_path():
    from bugsi_daemon.hardware.ids_event_camera import IDSEventCamera
    cam = IDSEventCamera(device_path="auto")
    assert cam._configured_path == "auto"
    assert cam._device_path == ""


def test_implements_event_camera_interface():
    from bugsi_daemon.hardware.ids_event_camera import IDSEventCamera
    assert issubclass(IDSEventCamera, EventCameraInterface)


async def test_initialize_raises_without_sdk():
    from bugsi_daemon.hardware.ids_event_camera import IDSEventCamera
    cam = IDSEventCamera()
    with pytest.raises((NotImplementedError, ImportError)):
        await cam.initialize()
