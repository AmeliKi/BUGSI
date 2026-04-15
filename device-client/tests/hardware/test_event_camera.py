from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from bugsi_daemon.hardware.base import EventCameraInterface
from bugsi_daemon.hardware.event_camera import (
    PropheseeEventCamera,
    _RETRY_BACKOFF_FACTOR,
    _RETRY_BASE_DELAY,
    _RETRY_MAX_DELAY,
)
from bugsi_daemon.hardware_mock.event_camera import MockEventCamera


# ---------------------------------------------------------------------------
# PropheseeEventCamera – device path resolution
# ---------------------------------------------------------------------------

class TestResolveDevicePath:
    def test_passthrough_explicit_path(self):
        assert PropheseeEventCamera._resolve_device_path("/dev/video2") == "/dev/video2"

    def test_auto_finds_genx320_in_sysfs(self, tmp_path):
        # Simulate sysfs layout: /sys/class/video4linux/video3/name
        v4l_dir = tmp_path / "video4linux" / "video3"
        v4l_dir.mkdir(parents=True)
        (v4l_dir / "name").write_text("genx320 10-003c\n")

        pattern = str(tmp_path / "video4linux" / "video*" / "name")
        with patch("bugsi_daemon.hardware.event_camera.glob.glob", return_value=sorted([str(v4l_dir / "name")])):
            result = PropheseeEventCamera._resolve_device_path("auto")
        assert result == "/dev/video3"

    def test_auto_falls_back_when_no_sysfs_match(self):
        with patch("bugsi_daemon.hardware.event_camera.glob.glob", return_value=[]):
            result = PropheseeEventCamera._resolve_device_path("auto")
        assert result == "/dev/video0"

    def test_init_stores_resolved_path(self):
        with patch.object(PropheseeEventCamera, "_resolve_device_path", return_value="/dev/video5"):
            cam = PropheseeEventCamera(device_path="auto")
        assert cam._device_path == "/dev/video5"
        assert cam._configured_path == "auto"

    def test_init_stores_explicit_configured_path(self):
        with patch.object(PropheseeEventCamera, "_resolve_device_path", return_value="/dev/video2"):
            cam = PropheseeEventCamera(device_path="/dev/video2")
        assert cam._configured_path == "/dev/video2"
        assert cam._device_path == "/dev/video2"


# ---------------------------------------------------------------------------
# MockEventCamera – accepts **kwargs
# ---------------------------------------------------------------------------

class TestMockEventCameraKwargs:
    def test_accepts_hardware_kwargs(self):
        """MockEventCamera should silently ignore hardware-specific config."""
        cam = MockEventCamera(
            device_path="auto",
            event_threshold=500,
            detection_window_ms=50,
            min_cluster_area=100,
        )
        assert isinstance(cam, EventCameraInterface)


# ---------------------------------------------------------------------------
# MockEventCamera – original test suite
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestMockEventCamera:
    async def test_implements_interface(self):
        assert isinstance(MockEventCamera(), EventCameraInterface)

    async def test_starts_not_powered(self):
        cam = MockEventCamera()
        assert not cam.is_powered()
        assert not cam.is_detecting()

    async def test_power_on_off(self):
        cam = MockEventCamera()
        await cam.power_on()
        assert cam.is_powered()
        await cam.power_off()
        assert not cam.is_powered()

    async def test_start_stop_detection(self):
        cam = MockEventCamera()
        await cam.initialize()
        await cam.start_detection()
        assert cam.is_detecting()
        await cam.stop_detection()
        assert not cam.is_detecting()

    async def test_start_detection_requires_power(self):
        cam = MockEventCamera()
        with pytest.raises(RuntimeError):
            await cam.start_detection()

    async def test_wait_for_detection_returns_bool(self):
        cam = MockEventCamera(detection_probability=1.0, min_wait_seconds=0.01, max_wait_seconds=0.02)
        await cam.initialize()
        await cam.start_detection()
        result = await cam.wait_for_detection(timeout=1.0)
        assert isinstance(result, bool)

    async def test_wait_for_detection_when_not_detecting(self):
        cam = MockEventCamera()
        await cam.initialize()
        result = await cam.wait_for_detection(timeout=0.1)
        assert result is False

    async def test_wait_for_detection_with_timeout(self):
        cam = MockEventCamera(detection_probability=0.0, min_wait_seconds=10, max_wait_seconds=20)
        await cam.initialize()
        await cam.start_detection()
        result = await cam.wait_for_detection(timeout=0.1)
        assert result is False

    async def test_capture_event_frame_returns_array(self):
        cam = MockEventCamera()
        await cam.initialize()
        frame = await cam.capture_event_frame()
        assert isinstance(frame, np.ndarray)
        assert frame.ndim == 3
        assert frame.shape[2] == 3

    async def test_shutdown_stops_everything(self):
        cam = MockEventCamera()
        await cam.initialize()
        await cam.start_detection()
        await cam.shutdown()
        assert not cam.is_powered()
        assert not cam.is_detecting()


# ---------------------------------------------------------------------------
# PropheseeEventCamera – detection loop retry behaviour
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestDetectionLoopRetry:
    async def test_re_resolves_on_open_failure_with_auto(self):
        """When configured as 'auto', _resolve_device_path is called on each retry."""
        resolve_calls = []

        def mock_resolve(path):
            resolve_calls.append(path)
            return "/dev/video0"

        with patch.object(PropheseeEventCamera, "_resolve_device_path", side_effect=mock_resolve):
            cam = PropheseeEventCamera(device_path="auto")

        # Reset call tracking (constructor called resolve once)
        resolve_calls.clear()
        cam._detecting = True

        call_count = 0

        def failing_iterator(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count >= 3:
                cam._detecting = False
            raise OSError("Failed to open camera")

        mock_module = MagicMock()
        mock_module.EventsIterator = MagicMock(side_effect=failing_iterator)

        with patch.object(PropheseeEventCamera, "_resolve_device_path", side_effect=mock_resolve):
            with patch("bugsi_daemon.hardware.event_camera.asyncio.sleep", new_callable=AsyncMock):
                with patch.dict("sys.modules", {"metavision_core": MagicMock(), "metavision_core.event_io": mock_module}):
                    await cam._detection_loop()

        # _resolve_device_path should have been called on each attempt
        assert len(resolve_calls) >= 2

    async def test_no_re_resolve_with_explicit_path(self):
        """When device_path is explicit, it is not re-resolved on retry."""
        resolve_calls = []
        original_resolve = PropheseeEventCamera._resolve_device_path

        def tracking_resolve(path):
            resolve_calls.append(path)
            return original_resolve(path)

        with patch.object(PropheseeEventCamera, "_resolve_device_path", side_effect=tracking_resolve):
            cam = PropheseeEventCamera(device_path="/dev/video2")

        resolve_calls.clear()
        cam._detecting = True

        call_count = 0

        def failing_iterator(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            cam._detecting = False
            raise OSError("stop")

        mock_iterator_cls = MagicMock(side_effect=failing_iterator)
        with patch.object(PropheseeEventCamera, "_resolve_device_path", side_effect=tracking_resolve):
            with patch("bugsi_daemon.hardware.event_camera.asyncio.sleep", new_callable=AsyncMock):
                with patch.dict("sys.modules", {"metavision_core.event_io": MagicMock(EventsIterator=mock_iterator_cls)}):
                    await cam._detection_loop()

        # Should NOT have called _resolve_device_path during the loop
        assert len(resolve_calls) == 0

    async def test_backoff_increases_on_repeated_failures(self):
        """Retry delay doubles on each failure, up to the max."""
        with patch.object(PropheseeEventCamera, "_resolve_device_path", return_value="/dev/video0"):
            cam = PropheseeEventCamera(device_path="auto")

        cam._detecting = True
        sleep_delays = []
        call_count = 0

        async def mock_sleep(delay):
            sleep_delays.append(delay)

        def failing_iterator(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count >= 5:
                cam._detecting = False
            raise OSError("Failed to open camera")

        mock_iterator_cls = MagicMock(side_effect=failing_iterator)
        with patch.object(PropheseeEventCamera, "_resolve_device_path", return_value="/dev/video0"):
            with patch("bugsi_daemon.hardware.event_camera.asyncio.sleep", side_effect=mock_sleep):
                with patch.dict("sys.modules", {"metavision_core.event_io": MagicMock(EventsIterator=mock_iterator_cls)}):
                    await cam._detection_loop()

        assert len(sleep_delays) >= 3
        assert sleep_delays[0] == _RETRY_BASE_DELAY
        assert sleep_delays[1] == _RETRY_BASE_DELAY * _RETRY_BACKOFF_FACTOR
        assert sleep_delays[2] == _RETRY_BASE_DELAY * _RETRY_BACKOFF_FACTOR ** 2
        # Verify cap
        for d in sleep_delays:
            assert d <= _RETRY_MAX_DELAY
