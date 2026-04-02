from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock

import numpy as np
import pytest

from bugsi_daemon.hardware.base import STILL_CAMERA_REGISTRY, StillCameraInterface


def test_ids_rgb_registered_in_registry():
    import bugsi_daemon.hardware.ids_camera  # noqa: F401
    assert "ids_rgb" in STILL_CAMERA_REGISTRY


def test_constructor_accepts_config_params():
    from bugsi_daemon.hardware.ids_camera import IDSRGBCamera
    cam = IDSRGBCamera(
        resolution_width=1920,
        resolution_height=1080,
        camera_id=0,
        autofocus_mode="continuous",
    )
    assert cam._width == 1920
    assert cam._height == 1080


def test_is_open_initially_false():
    from bugsi_daemon.hardware.ids_camera import IDSRGBCamera
    cam = IDSRGBCamera()
    assert cam.is_open() is False


def test_open_raises_not_implemented_without_sdk():
    from bugsi_daemon.hardware.ids_camera import IDSRGBCamera
    cam = IDSRGBCamera()
    with pytest.raises((NotImplementedError, ImportError, RuntimeError)):
        cam.open()


def test_capture_raises_when_not_open():
    from bugsi_daemon.hardware.ids_camera import IDSRGBCamera
    cam = IDSRGBCamera()
    with pytest.raises(RuntimeError, match="not open"):
        cam.capture()


def test_implements_still_camera_interface():
    from bugsi_daemon.hardware.ids_camera import IDSRGBCamera
    assert issubclass(IDSRGBCamera, StillCameraInterface)


def test_constructor_accepts_all_new_params():
    from bugsi_daemon.hardware.ids_camera import IDSRGBCamera
    cam = IDSRGBCamera(
        resolution_width=5136,
        resolution_height=3856,
        camera_id=0,
        exposure_us=5000,
        gain_db=3.0,
        white_balance="off",
        balance_ratio_red=1.5,
        balance_ratio_green=1.0,
        balance_ratio_blue=1.8,
        gamma=0.8,
        black_level=2.5,
        acquisition_frame_rate=10.0,
        binning_horizontal=2,
        binning_vertical=2,
    )
    assert cam._width == 5136
    assert cam._height == 3856
    assert cam._white_balance == "off"
    assert cam._balance_ratio_red == 1.5
    assert cam._balance_ratio_green == 1.0
    assert cam._balance_ratio_blue == 1.8
    assert cam._gamma == 0.8
    assert cam._black_level == 2.5
    assert cam._acquisition_frame_rate == 10.0
    assert cam._binning_h == 2
    assert cam._binning_v == 2


def test_defaults_match_ar2020_sensor():
    from bugsi_daemon.hardware.ids_camera import IDSRGBCamera
    cam = IDSRGBCamera()
    assert cam._width == 5136
    assert cam._height == 3856
    assert cam._white_balance == "auto"
    assert cam._gamma == 1.0
    assert cam._black_level == 0.0
    assert cam._acquisition_frame_rate == 0.0
    assert cam._binning_h == 1
    assert cam._binning_v == 1


def test_autofocus_mode_accepted_but_not_stored():
    from bugsi_daemon.hardware.ids_camera import IDSRGBCamera
    cam = IDSRGBCamera(autofocus_mode="manual")
    # autofocus_mode is accepted for compatibility but not stored
    assert not hasattr(cam, "_autofocus_mode")


# ---------------------------------------------------------------------------
# Helpers for mocking GenICam node maps
# ---------------------------------------------------------------------------

def _make_mock_node_map(missing_nodes=None):
    """Create a mock node map where specified nodes raise on FindNode."""
    missing = set(missing_nodes or [])
    nodes = {}

    def find_node(name):
        if name in missing:
            raise Exception(f"Node '{name}' not found")
        if name not in nodes:
            node = MagicMock()
            node.Minimum.return_value = 0.0
            node.Maximum.return_value = 1_000_000.0
            node.Value.return_value = 0.0
            nodes[name] = node
        return nodes[name]

    nm = MagicMock()
    nm.FindNode.side_effect = find_node
    return nm, nodes


# ---------------------------------------------------------------------------
# Tests: missing auto-mode nodes should not prevent manual values
# ---------------------------------------------------------------------------

def test_exposure_set_when_exposure_auto_missing():
    from bugsi_daemon.hardware.ids_camera import IDSRGBCamera
    cam = IDSRGBCamera(exposure_us=5000)
    nm, nodes = _make_mock_node_map(missing_nodes=["ExposureAuto"])
    cam._node_map_remote = nm
    cam._apply_exposure_gain()

    nodes["ExposureTime"].SetValue.assert_called_once_with(5000)


def test_gain_set_when_gain_auto_missing():
    from bugsi_daemon.hardware.ids_camera import IDSRGBCamera
    cam = IDSRGBCamera(gain_db=3.0)
    nm, nodes = _make_mock_node_map(missing_nodes=["GainAuto"])
    cam._node_map_remote = nm
    cam._apply_exposure_gain()

    nodes["Gain"].SetValue.assert_called_once_with(3.0)


def test_balance_ratio_set_when_balance_white_auto_missing():
    from bugsi_daemon.hardware.ids_camera import IDSRGBCamera
    cam = IDSRGBCamera(white_balance="off", balance_ratio_red=1.5)
    nm, nodes = _make_mock_node_map(missing_nodes=["BalanceWhiteAuto"])
    cam._node_map_remote = nm
    cam._apply_white_balance()

    nodes["BalanceRatio"].SetValue.assert_called()


def test_exposure_auto_set_to_off_when_available():
    from bugsi_daemon.hardware.ids_camera import IDSRGBCamera
    cam = IDSRGBCamera(exposure_us=5000)
    nm, nodes = _make_mock_node_map()
    cam._node_map_remote = nm
    cam._apply_exposure_gain()

    nodes["ExposureAuto"].SetCurrentEntry.assert_called_once()
    nodes["ExposureTime"].SetValue.assert_called_once_with(5000)


def test_auto_exposure_no_crash_when_node_missing():
    from bugsi_daemon.hardware.ids_camera import IDSRGBCamera
    cam = IDSRGBCamera(exposure_us=0)
    nm, nodes = _make_mock_node_map(missing_nodes=["ExposureAuto"])
    cam._node_map_remote = nm
    cam._apply_exposure_gain()

    # ExposureTime gets an initial value for sw auto-exposure
    nodes["ExposureTime"].SetValue.assert_called_once()
    assert cam._sw_auto_exposure is True


def test_auto_gain_no_crash_when_node_missing():
    from bugsi_daemon.hardware.ids_camera import IDSRGBCamera
    cam = IDSRGBCamera(gain_db=0.0)
    nm, nodes = _make_mock_node_map(missing_nodes=["GainAuto"])
    cam._node_map_remote = nm
    cam._apply_exposure_gain()

    # Gain gets an initial value for sw auto-exposure
    nodes["Gain"].SetValue.assert_called_once()
    assert cam._sw_auto_exposure is True


def test_sw_auto_exposure_flag_false_when_hw_auto_available():
    from bugsi_daemon.hardware.ids_camera import IDSRGBCamera
    cam = IDSRGBCamera(exposure_us=0, gain_db=0.0)
    nm, nodes = _make_mock_node_map()
    cam._node_map_remote = nm
    cam._apply_exposure_gain()

    assert cam._sw_auto_exposure is False


# ---------------------------------------------------------------------------
# Tests: software auto-calibration
# ---------------------------------------------------------------------------

def _make_mock_ipl():
    """Create a mock IPL module that returns frames with controllable brightness."""
    ipl = MagicMock()
    return ipl


def _make_mock_datastream(frames):
    """Create a mock datastream that returns buffers yielding the given frames.

    *frames* is a list of mean brightness values. Each call to
    WaitForFinishedBuffer returns a buffer whose converted image has that
    mean brightness.
    """
    ds = MagicMock()
    buffers = []
    for _ in frames:
        buf = MagicMock()
        buffers.append(buf)
    ds.WaitForFinishedBuffer.side_effect = buffers
    return ds, buffers


def test_auto_calibrate_converges_on_dark_image():
    from bugsi_daemon.hardware.ids_camera import IDSRGBCamera

    cam = IDSRGBCamera(exposure_us=0)
    nm, nodes = _make_mock_node_map(missing_nodes=["ExposureAuto", "GainAuto"])
    cam._node_map_remote = nm
    cam._apply_exposure_gain()

    # Simulate frames getting brighter as exposure increases
    brightness_sequence = [30.0, 80.0, 130.0]

    ipl = MagicMock()
    cam._ipl = ipl

    ds = MagicMock()
    mock_buffers = [MagicMock() for _ in brightness_sequence]
    ds.WaitForFinishedBuffer.side_effect = mock_buffers
    cam._datastream = ds

    # Make IPL return frames with controlled brightness
    call_count = [0]
    def fake_convert(_fmt):
        idx = call_count[0]
        call_count[0] += 1
        brightness = brightness_sequence[min(idx, len(brightness_sequence) - 1)]
        frame_mock = MagicMock()
        frame_mock.get_numpy_3D.return_value = np.full((10, 10, 3), brightness, dtype=np.uint8)
        return frame_mock

    raw_mock = MagicMock()
    raw_mock.ConvertTo.side_effect = fake_convert
    ipl.Image.CreateFromSizeAndBuffer.return_value = raw_mock

    # Set initial ExposureTime value
    nodes["ExposureTime"].Value.return_value = 20000.0
    nodes["ExposureTime"].Minimum.return_value = 100.0
    nodes["ExposureTime"].Maximum.return_value = 500000.0
    nodes["Gain"].Value.return_value = 2.0
    nodes["Gain"].Minimum.return_value = 0.0
    nodes["Gain"].Maximum.return_value = 24.0

    cam._auto_calibrate(target_brightness=128.0, tolerance=25.0)

    # Exposure should have been increased (dark -> bright)
    assert nodes["ExposureTime"].SetValue.call_count >= 2


def test_auto_calibrate_already_bright_enough():
    from bugsi_daemon.hardware.ids_camera import IDSRGBCamera

    cam = IDSRGBCamera(exposure_us=0)
    nm, nodes = _make_mock_node_map(missing_nodes=["ExposureAuto", "GainAuto"])
    cam._node_map_remote = nm
    cam._apply_exposure_gain()

    ipl = MagicMock()
    cam._ipl = ipl

    ds = MagicMock()
    buf = MagicMock()
    ds.WaitForFinishedBuffer.return_value = buf
    cam._datastream = ds

    # Frame already at target brightness
    frame_mock = MagicMock()
    frame_mock.get_numpy_3D.return_value = np.full((10, 10, 3), 130, dtype=np.uint8)
    raw_mock = MagicMock()
    raw_mock.ConvertTo.return_value = frame_mock
    ipl.Image.CreateFromSizeAndBuffer.return_value = raw_mock

    nodes["ExposureTime"].Value.return_value = 20000.0
    nodes["ExposureTime"].Minimum.return_value = 100.0
    nodes["ExposureTime"].Maximum.return_value = 500000.0
    # Reset call count from _apply_exposure_gain initial setup
    nodes["ExposureTime"].SetValue.reset_mock()

    cam._auto_calibrate(target_brightness=128.0, tolerance=25.0)

    # Should converge immediately — no exposure adjustment needed
    nodes["ExposureTime"].SetValue.assert_not_called()
