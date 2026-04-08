"""Tests for the zigpy-based ZigbeeClimateSensor (replaces zigbee2mqtt)."""
import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bugsi_daemon.hardware.climate import (
    ZigbeeClimateSensor,
    _AppDeviceListener,
    _ClimateClusterListener,
    _TuyaClusterListener,
    _CLUSTER_TEMPERATURE,
    _CLUSTER_HUMIDITY,
    _CLUSTER_POWER_CONFIG,
    _CLUSTER_TUYA,
    _ATTR_MEASURED_VALUE,
    _ATTR_BATTERY_PERCENT,
    _ATTR_BATTERY_VOLTAGE,
    _TUYA_DP_TEMPERATURE,
    _TUYA_DP_HUMIDITY,
    _TUYA_DP_BATTERY,
    _TUYA_DP_TEMPERATURE_ALT,
    _TUYA_DP_HUMIDITY_ALT,
    _TUYA_DP_BATTERY_ALT,
)


def _make_sensor(**kwargs) -> ZigbeeClimateSensor:
    defaults = {"serial_port": "auto", "adapter": "ezsp"}
    defaults.update(kwargs)
    return ZigbeeClimateSensor(**defaults)


@pytest.mark.asyncio
class TestInitialize:
    async def test_raises_when_zigpy_not_installed(self):
        sensor = _make_sensor()
        with patch.dict("sys.modules", {"zigpy.application": None, "bellows.zigbee.application": None}):
            with pytest.raises((NotImplementedError, ImportError)):
                await sensor.initialize()

    async def test_succeeds_when_zigpy_installed(self):
        sensor = _make_sensor()
        with patch.dict("sys.modules", {
            "zigpy.application": MagicMock(),
            "bellows.zigbee.application": MagicMock(),
        }):
            await sensor.initialize()


@pytest.mark.asyncio
class TestPowerOn:
    async def test_creates_controller_app(self):
        sensor = _make_sensor(serial_port="/dev/ttyUSB0")

        mock_app = AsyncMock()
        mock_app.devices = {}
        mock_app.startup = AsyncMock()

        with patch.object(sensor, "_uhubctl_power", AsyncMock()):
            with patch("asyncio.sleep", AsyncMock()):
                with patch(
                    "bugsi_daemon.hardware.climate.ZigbeeClimateSensor._start_zigpy",
                    AsyncMock(),
                ) as mock_start:
                    await sensor.power_on()

                    mock_start.assert_called_once_with("/dev/ttyUSB0")
                    assert sensor.is_powered()
                    assert sensor.is_healthy()

    async def test_auto_detects_serial_port(self):
        sensor = _make_sensor(serial_port="auto")

        with patch.object(sensor, "_uhubctl_power", AsyncMock()):
            with patch("asyncio.sleep", AsyncMock()):
                with patch.object(
                    ZigbeeClimateSensor,
                    "_auto_detect_serial_port",
                    return_value="/dev/serial/by-id/usb-Sonoff-Zigbee",
                ):
                    with patch.object(sensor, "_start_zigpy", AsyncMock()) as mock_start:
                        await sensor.power_on()

                        mock_start.assert_called_once_with("/dev/serial/by-id/usb-Sonoff-Zigbee")

    async def test_raises_when_auto_detect_returns_none(self):
        sensor = _make_sensor(serial_port="auto")

        with patch.object(sensor, "_uhubctl_power", AsyncMock()):
            with patch("asyncio.sleep", AsyncMock()):
                with patch.object(
                    ZigbeeClimateSensor,
                    "_auto_detect_serial_port",
                    return_value=None,
                ):
                    with pytest.raises(
                        FileNotFoundError, match="No Zigbee serial port detected"
                    ):
                        await sensor.power_on()

        # USB hub was powered on, so _powered should be True
        assert sensor.is_powered()
        assert not sensor.is_healthy()

    async def test_uhubctl_failure_raises_on_power_on(self):
        sensor = _make_sensor(serial_port="auto")

        with patch.object(
            sensor, "_uhubctl_power", AsyncMock(side_effect=OSError("uhubctl failed"))
        ):
            with pytest.raises(OSError, match="uhubctl failed"):
                await sensor.power_on()


class _FakeTransientConnectionError(Exception):
    """Stand-in for zigpy.exceptions.TransientConnectionError in tests."""


def _mock_bellows(mock_ctrl):
    """Inject a mock bellows module into sys.modules so _start_zigpy's
    ``from bellows.zigbee.application import ControllerApplication`` works
    without bellows installed."""
    mod_app = MagicMock()
    mod_app.ControllerApplication = mock_ctrl
    mod_zigbee = MagicMock()
    mod_zigbee.application = mod_app
    mod_bellows = MagicMock()
    mod_bellows.zigbee = mod_zigbee
    mod_bellows.zigbee.application = mod_app

    mod_zigpy_exc = MagicMock()
    mod_zigpy_exc.TransientConnectionError = _FakeTransientConnectionError

    return patch.dict("sys.modules", {
        "bellows": mod_bellows,
        "bellows.zigbee": mod_zigbee,
        "bellows.zigbee.application": mod_app,
        "zigpy": MagicMock(),
        "zigpy.exceptions": mod_zigpy_exc,
    })


@pytest.mark.asyncio
class TestStartZigpy:
    """Regression tests for _start_zigpy() — must use ControllerApplication.new()
    with auto_form=True and NOT call startup() separately, because new() already
    calls startup() internally. Calling it twice locks the serial port."""

    async def test_calls_new_with_auto_form_true(self, tmp_path):
        sensor = _make_sensor(database_path=str(tmp_path / "zigbee.db"))
        fake_port = tmp_path / "ttyUSB0"
        fake_port.touch()

        mock_app = AsyncMock()
        mock_app.startup = AsyncMock()
        MockCtrl = MagicMock()
        MockCtrl.new = AsyncMock(return_value=mock_app)

        with _mock_bellows(MockCtrl):
            await sensor._start_zigpy(str(fake_port))

        MockCtrl.new.assert_called_once()
        _, kwargs = MockCtrl.new.call_args
        assert kwargs.get("auto_form") is True

        # startup() must NOT be called separately — new() handles it
        mock_app.startup.assert_not_called()

    async def test_passes_correct_config(self, tmp_path):
        db = tmp_path / "zigbee.db"
        sensor = _make_sensor(
            database_path=str(db),
            network_channel=15,
        )
        fake_port = tmp_path / "ttyUSB0"
        fake_port.touch()

        mock_app = AsyncMock()
        MockCtrl = MagicMock()
        MockCtrl.new = AsyncMock(return_value=mock_app)

        with _mock_bellows(MockCtrl):
            await sensor._start_zigpy(str(fake_port))

        config_arg = MockCtrl.new.call_args[0][0]
        assert config_arg["database_path"] == str(db)
        assert config_arg["device"]["path"] == str(fake_port)
        assert config_arg["network"]["channel"] == 15

    async def test_retries_on_broken_pipe_error(self, tmp_path):
        sensor = _make_sensor(database_path=str(tmp_path / "zigbee.db"))
        fake_port = tmp_path / "ttyUSB0"
        fake_port.touch()
        mock_app = AsyncMock()

        call_count = 0

        async def fail_twice(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise BrokenPipeError("Broken pipe")
            return mock_app

        MockCtrl = MagicMock()
        MockCtrl.new = AsyncMock(side_effect=fail_twice)

        with _mock_bellows(MockCtrl):
            with patch("asyncio.sleep", AsyncMock()) as mock_sleep:
                await sensor._start_zigpy(str(fake_port))

        assert MockCtrl.new.call_count == 3
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(2.0)
        mock_sleep.assert_any_call(4.0)
        assert sensor._app is mock_app

    async def test_retries_exhausted_raises(self, tmp_path):
        sensor = _make_sensor(database_path=str(tmp_path / "zigbee.db"))
        fake_port = tmp_path / "ttyUSB0"
        fake_port.touch()

        MockCtrl = MagicMock()
        MockCtrl.new = AsyncMock(side_effect=BrokenPipeError("Broken pipe"))

        with _mock_bellows(MockCtrl):
            with patch("asyncio.sleep", AsyncMock()):
                with pytest.raises(BrokenPipeError):
                    await sensor._start_zigpy(str(fake_port))

        assert MockCtrl.new.call_count == 3
        assert sensor._app is None

    async def test_non_retryable_error_no_retry(self, tmp_path):
        sensor = _make_sensor(database_path=str(tmp_path / "zigbee.db"))
        fake_port = tmp_path / "ttyUSB0"
        fake_port.touch()

        MockCtrl = MagicMock()
        MockCtrl.new = AsyncMock(side_effect=ValueError("bad config"))

        with _mock_bellows(MockCtrl):
            with patch("asyncio.sleep", AsyncMock()) as mock_sleep:
                with pytest.raises(ValueError, match="bad config"):
                    await sensor._start_zigpy(str(fake_port))

        assert MockCtrl.new.call_count == 1
        mock_sleep.assert_not_called()

    async def test_fails_fast_on_missing_serial_port(self, tmp_path):
        sensor = _make_sensor(database_path=str(tmp_path / "zigbee.db"))

        MockCtrl = MagicMock()
        MockCtrl.new = AsyncMock()

        with _mock_bellows(MockCtrl):
            with pytest.raises(FileNotFoundError, match="/dev/ttyNONEXISTENT"):
                await sensor._start_zigpy("/dev/ttyNONEXISTENT")

        # ControllerApplication.new() should never have been called
        MockCtrl.new.assert_not_called()

    async def test_no_retry_on_file_not_found(self, tmp_path):
        """FileNotFoundError from ControllerApplication.new() must not retry."""
        sensor = _make_sensor(database_path=str(tmp_path / "zigbee.db"))
        fake_port = tmp_path / "ttyUSB0"
        fake_port.touch()

        MockCtrl = MagicMock()
        MockCtrl.new = AsyncMock(
            side_effect=FileNotFoundError("/dev/ttyUSB0")
        )

        with _mock_bellows(MockCtrl):
            with patch("asyncio.sleep", AsyncMock()) as mock_sleep:
                with pytest.raises(FileNotFoundError):
                    await sensor._start_zigpy(str(fake_port))

        # Should fail on the first attempt, no retries
        assert MockCtrl.new.call_count == 1
        mock_sleep.assert_not_called()


@pytest.mark.asyncio
class TestPowerOnErrorPropagation:
    async def test_power_on_raises_on_zigpy_failure(self):
        sensor = _make_sensor(serial_port="/dev/ttyUSB0")

        with patch.object(sensor, "_uhubctl_power", AsyncMock()):
            with patch("asyncio.sleep", AsyncMock()):
                with patch.object(
                    sensor, "_start_zigpy",
                    AsyncMock(side_effect=OSError("serial error")),
                ):
                    with pytest.raises(OSError, match="serial error"):
                        await sensor.power_on()

        assert sensor.is_powered()
        assert not sensor.is_healthy()
        assert sensor._app is None

    async def test_power_off_works_after_failed_power_on(self):
        sensor = _make_sensor(serial_port="/dev/ttyUSB0")

        with patch.object(sensor, "_uhubctl_power", AsyncMock()) as mock_uhub:
            with patch("asyncio.sleep", AsyncMock()):
                with patch.object(
                    sensor, "_start_zigpy",
                    AsyncMock(side_effect=OSError("serial error")),
                ):
                    with pytest.raises(OSError):
                        await sensor.power_on()

            await sensor.power_off()

        assert not sensor.is_powered()
        # uhubctl called for power on AND power off
        assert mock_uhub.call_count == 2


@pytest.mark.asyncio
class TestUhubctlSafety:
    async def test_power_off_skips_all_hubs_when_dongle_unknown(self):
        """power_off must NOT call _uhubctl_power_all_hubs — that kills all USB devices."""
        sensor = _make_sensor(serial_port="/dev/ttyUSB0")
        # Simulate: dongle hub/port never detected
        sensor._usb_hub = None
        sensor._usb_port = None

        with patch.object(sensor, "_auto_detect_zigbee_usb", AsyncMock()):
            with patch.object(sensor, "_uhubctl_power_all_hubs", AsyncMock()) as mock_all:
                with patch.object(
                    ZigbeeClimateSensor, "_load_usb_cache", return_value=(None, None),
                ):
                    await sensor._uhubctl_power("off")

        mock_all.assert_not_called()

    async def test_power_on_uses_all_hubs_for_detection(self):
        """power_on may power on all hubs to find the dongle."""
        sensor = _make_sensor(serial_port="/dev/ttyUSB0")
        sensor._usb_hub = None
        sensor._usb_port = None

        with patch.object(sensor, "_auto_detect_zigbee_usb", AsyncMock()):
            with patch.object(sensor, "_uhubctl_power_all_hubs", AsyncMock()) as mock_all:
                with patch.object(
                    ZigbeeClimateSensor, "_load_usb_cache", return_value=(None, None),
                ):
                    with patch("asyncio.sleep", AsyncMock()):
                        await sensor._uhubctl_power("on")

        mock_all.assert_called_once_with("on")


@pytest.mark.asyncio
class TestPowerOff:
    async def test_shuts_down_controller(self):
        sensor = _make_sensor()
        sensor._powered = True
        sensor._healthy = True
        mock_app = AsyncMock()
        sensor._app = mock_app

        with patch.object(sensor, "_uhubctl_power", AsyncMock()):
            await sensor.power_off()

        mock_app.shutdown.assert_called_once()
        assert sensor._app is None
        assert not sensor.is_powered()
        assert not sensor.is_healthy()


@pytest.mark.asyncio
class TestClusterListener:
    async def test_temperature_update(self):
        sensor = _make_sensor()
        listener = _ClimateClusterListener(sensor, _CLUSTER_TEMPERATURE)

        # ZCL temperature is in 0.01°C units
        listener.attribute_updated(_ATTR_MEASURED_VALUE, 2350)

        assert sensor._last_reading["temperature"] == 23.5

    async def test_humidity_update(self):
        sensor = _make_sensor()
        listener = _ClimateClusterListener(sensor, _CLUSTER_HUMIDITY)

        # ZCL humidity is in 0.01% units
        listener.attribute_updated(_ATTR_MEASURED_VALUE, 6520)

        assert sensor._last_reading["humidity"] == 65.2

    async def test_battery_percent_update(self):
        sensor = _make_sensor()
        listener = _ClimateClusterListener(sensor, _CLUSTER_POWER_CONFIG)

        # ZCL battery percent is 0-200 (half-percent resolution)
        listener.attribute_updated(_ATTR_BATTERY_PERCENT, 180)

        assert sensor._last_reading["sensor_battery"] == 90

    async def test_battery_voltage_update(self):
        sensor = _make_sensor()
        listener = _ClimateClusterListener(sensor, _CLUSTER_POWER_CONFIG)

        # ZCL battery voltage is in 100mV units
        listener.attribute_updated(_ATTR_BATTERY_VOLTAGE, 30)

        assert sensor._last_reading["sensor_voltage"] == 3000

    async def test_ignores_invalid_value(self):
        sensor = _make_sensor()
        listener = _ClimateClusterListener(sensor, _CLUSTER_TEMPERATURE)

        # Should not raise
        listener.attribute_updated(_ATTR_MEASURED_VALUE, None)

        assert "temperature" not in sensor._last_reading


@pytest.mark.asyncio
class TestGetDevices:
    async def test_returns_empty_when_not_powered(self):
        sensor = _make_sensor()
        devices = await sensor.get_devices()
        assert devices == []

    async def test_returns_devices_from_app(self, tmp_path):
        import bugsi_daemon.hardware.climate as climate_mod
        name_file = tmp_path / "zigbee_names.json"
        name_file.write_text(json.dumps({"0xaabbccdd": "climate_sensor"}))
        original = climate_mod._NAME_MAP_PATH
        climate_mod._NAME_MAP_PATH = name_file

        try:
            sensor = _make_sensor()
            sensor._powered = True

            mock_dev = MagicMock()
            mock_dev.model = "SNZB-02WD"
            mock_dev.manufacturer = "SONOFF"
            mock_dev.last_seen = 1234567890
            mock_dev.node_desc = MagicMock()
            mock_dev.node_desc.is_coordinator = False

            mock_app = AsyncMock()
            mock_app.devices = {"0xaabbccdd": mock_dev}
            sensor._app = mock_app

            devices = await sensor.get_devices()

            assert len(devices) == 1
            assert devices[0]["friendly_name"] == "climate_sensor"
            assert devices[0]["model"] == "SNZB-02WD"
            assert devices[0]["vendor"] == "SONOFF"
            assert devices[0]["type"] == "EndDevice"
            assert devices[0]["available"] is True
        finally:
            climate_mod._NAME_MAP_PATH = original


@pytest.mark.asyncio
class TestSerialPortAutoDetect:
    async def test_detects_sonoff_device(self, tmp_path):
        serial_dir = tmp_path / "serial" / "by-id"
        serial_dir.mkdir(parents=True)
        sonoff_link = serial_dir / "usb-Itead_Sonoff_Zigbee_3.0_USB_Dongle_Plus_V2-if00-port0"
        sonoff_link.touch()

        with patch("bugsi_daemon.hardware.climate.Path") as mock_path_cls:
            # We need the Path("/dev/serial/by-id") call to return our tmp dir
            def path_factory(p):
                if p == "/dev/serial/by-id":
                    return serial_dir
                if p == "/dev/ttyUSB0":
                    mock_p = MagicMock()
                    mock_p.exists.return_value = False
                    return mock_p
                return Path(p)
            mock_path_cls.side_effect = path_factory

            result = ZigbeeClimateSensor._auto_detect_serial_port()

        # Should find the Sonoff device (name contains 'sonoff' and 'zigbee')
        assert result is not None

    async def test_returns_none_when_no_serial_dir(self):
        with patch("bugsi_daemon.hardware.climate.Path") as mock_path_cls:
            mock_serial_dir = MagicMock()
            mock_serial_dir.is_dir.return_value = False
            mock_path_cls.return_value = mock_serial_dir

            result = ZigbeeClimateSensor._auto_detect_serial_port()

        assert result is None


@pytest.mark.asyncio
class TestNameMap:
    async def test_load_save_roundtrip(self, tmp_path):
        import bugsi_daemon.hardware.climate as climate_mod
        name_file = tmp_path / "zigbee_names.json"
        original = climate_mod._NAME_MAP_PATH
        climate_mod._NAME_MAP_PATH = name_file

        try:
            # Initially empty
            name_map = ZigbeeClimateSensor._load_name_map()
            assert name_map == {}

            # Save and reload
            ZigbeeClimateSensor._save_name_map({"0xaabb": "my_sensor"})
            name_map = ZigbeeClimateSensor._load_name_map()
            assert name_map == {"0xaabb": "my_sensor"}
        finally:
            climate_mod._NAME_MAP_PATH = original

    async def test_load_missing_file(self, tmp_path):
        import bugsi_daemon.hardware.climate as climate_mod
        original = climate_mod._NAME_MAP_PATH
        climate_mod._NAME_MAP_PATH = tmp_path / "nonexistent.json"

        try:
            name_map = ZigbeeClimateSensor._load_name_map()
            assert name_map == {}
        finally:
            climate_mod._NAME_MAP_PATH = original


@pytest.mark.asyncio
class TestConfigureReporting:
    async def test_configures_clusters(self):
        sensor = _make_sensor()

        mock_temp_cluster = AsyncMock()
        mock_humidity_cluster = AsyncMock()
        mock_power_cluster = AsyncMock()

        mock_endpoint = MagicMock()
        mock_endpoint.in_clusters = {
            _CLUSTER_TEMPERATURE: mock_temp_cluster,
            _CLUSTER_HUMIDITY: mock_humidity_cluster,
            _CLUSTER_POWER_CONFIG: mock_power_cluster,
        }

        mock_device = MagicMock()
        mock_device.endpoints = {0: MagicMock(), 1: mock_endpoint}
        mock_device.endpoints[0].in_clusters = {}  # ZDO has no relevant clusters

        await sensor._configure_reporting(mock_device)

        mock_temp_cluster.configure_reporting.assert_called_once()
        mock_humidity_cluster.configure_reporting.assert_called_once()
        mock_power_cluster.configure_reporting.assert_called_once()

    async def test_handles_reporting_failure(self):
        sensor = _make_sensor()

        mock_cluster = AsyncMock()
        mock_cluster.configure_reporting.side_effect = Exception("Not supported")

        mock_endpoint = MagicMock()
        mock_endpoint.in_clusters = {_CLUSTER_TEMPERATURE: mock_cluster}

        mock_device = MagicMock()
        mock_device.endpoints = {1: mock_endpoint}

        # Should not raise
        await sensor._configure_reporting(mock_device)


@pytest.mark.asyncio
class TestAppDeviceListener:
    """Tests for auto-installing listeners when devices join after power_on."""

    async def test_device_initialized_installs_listeners(self):
        sensor = _make_sensor()

        mock_temp_cluster = MagicMock()
        mock_humidity_cluster = MagicMock()
        mock_endpoint = MagicMock()
        mock_endpoint.in_clusters = {
            _CLUSTER_TEMPERATURE: mock_temp_cluster,
            _CLUSTER_HUMIDITY: mock_humidity_cluster,
        }

        mock_device = MagicMock()
        mock_device.ieee = "a4:c1:38:00:00:00:00:01"
        mock_device.endpoints = {0: MagicMock(), 1: mock_endpoint}

        listener = _AppDeviceListener(sensor)
        listener.device_initialized(mock_device)

        mock_temp_cluster.add_listener.assert_called_once()
        mock_humidity_cluster.add_listener.assert_called_once()

    async def test_device_initialized_ignores_non_climate(self):
        sensor = _make_sensor()

        mock_endpoint = MagicMock()
        mock_endpoint.in_clusters = {0x0006: MagicMock()}  # on_off cluster only

        mock_device = MagicMock()
        mock_device.ieee = "a4:c1:38:00:00:00:00:02"
        mock_device.endpoints = {0: MagicMock(), 1: mock_endpoint}

        listener = _AppDeviceListener(sensor)
        listener.device_initialized(mock_device)

        mock_endpoint.in_clusters[0x0006].add_listener.assert_not_called()

    async def test_device_joined_starts_monitor(self):
        sensor = _make_sensor()

        mock_device = MagicMock()
        mock_device.ieee = "a4:c1:38:00:00:00:00:03"
        mock_device.endpoints = {0: MagicMock()}  # no climate clusters yet

        listener = _AppDeviceListener(sensor)
        listener.device_joined(mock_device)

        # Monitor task should have been created
        assert len(listener._monitor_tasks) == 1
        # Cancel the task so it doesn't leak
        listener._monitor_tasks[0].cancel()

    async def test_monitor_installs_listeners_when_clusters_appear(self):
        """Simulates a device whose clusters become available after joining."""
        sensor = _make_sensor()

        mock_temp_cluster = MagicMock()
        mock_temp_cluster.read_attributes = AsyncMock(return_value=[{}, {}])
        mock_endpoint = MagicMock()
        # Start with no climate clusters
        mock_endpoint.in_clusters = {}

        mock_device = MagicMock()
        mock_device.ieee = "a4:c1:38:00:00:00:00:04"
        mock_device.endpoints = {0: MagicMock(), 1: mock_endpoint}

        listener = _AppDeviceListener(sensor)

        # Run the monitor with a short poll interval
        # After a brief delay, add the temperature cluster
        async def add_clusters_later():
            await asyncio.sleep(0.05)
            mock_endpoint.in_clusters = {_CLUSTER_TEMPERATURE: mock_temp_cluster}

        asyncio.get_event_loop().create_task(add_clusters_later())
        await listener._monitor_device(mock_device, poll_interval=0.03, max_wait=1.0)

        mock_temp_cluster.add_listener.assert_called_once()
        mock_temp_cluster.read_attributes.assert_called_once()

    async def test_monitor_times_out_without_clusters(self):
        """Monitor gives up after max_wait if no climate clusters appear."""
        sensor = _make_sensor()

        mock_endpoint = MagicMock()
        mock_endpoint.in_clusters = {0x0006: MagicMock()}  # non-climate only

        mock_device = MagicMock()
        mock_device.ieee = "a4:c1:38:00:00:00:00:05"
        mock_device.endpoints = {0: MagicMock(), 1: mock_endpoint}

        listener = _AppDeviceListener(sensor)
        await listener._monitor_device(mock_device, poll_interval=0.02, max_wait=0.05)

        # No climate clusters found, so no listeners installed
        mock_endpoint.in_clusters[0x0006].add_listener.assert_not_called()


@pytest.mark.asyncio
class TestWaitForReading:
    async def test_returns_reading_when_data_arrives(self):
        sensor = _make_sensor()
        temp_listener = _ClimateClusterListener(sensor, _CLUSTER_TEMPERATURE)
        hum_listener = _ClimateClusterListener(sensor, _CLUSTER_HUMIDITY)

        async def simulate_data():
            await asyncio.sleep(0.05)
            temp_listener.attribute_updated(_ATTR_MEASURED_VALUE, 2200)
            await asyncio.sleep(0.05)
            hum_listener.attribute_updated(_ATTR_MEASURED_VALUE, 6500)

        import asyncio
        asyncio.get_event_loop().create_task(simulate_data())
        reading = await sensor.wait_for_reading(timeout=2.0)

        assert reading["temperature"] == 22.0
        assert reading["humidity"] == 65.0

    async def test_returns_partial_on_timeout(self):
        """If only temperature arrives before timeout, return what we have."""
        sensor = _make_sensor()
        temp_listener = _ClimateClusterListener(sensor, _CLUSTER_TEMPERATURE)

        async def simulate_data():
            await asyncio.sleep(0.05)
            temp_listener.attribute_updated(_ATTR_MEASURED_VALUE, 2200)

        import asyncio
        asyncio.get_event_loop().create_task(simulate_data())
        reading = await sensor.wait_for_reading(timeout=0.3)

        assert reading["temperature"] == 22.0
        assert "humidity" not in reading

    async def test_returns_empty_on_timeout(self):
        sensor = _make_sensor()
        reading = await sensor.wait_for_reading(timeout=0.1)
        assert reading == {}

    async def test_data_event_set_on_attribute_update(self):
        sensor = _make_sensor()
        assert not sensor._data_event.is_set()

        listener = _ClimateClusterListener(sensor, _CLUSTER_HUMIDITY)
        listener.attribute_updated(_ATTR_MEASURED_VALUE, 5000)

        assert sensor._data_event.is_set()
        assert sensor._last_reading["humidity"] == 50.0


@pytest.mark.asyncio
class TestTuyaClusterListener:
    """Tests for Tuya TS0601 cluster 0xEF00 datapoint parsing."""

    def _make_tuya_frame(self, dp_id, dp_type, value_bytes, seq=0x0001):
        """Build a Tuya frame: [seq: 2 bytes][dp_id][dp_type][dp_len: 2 BE][dp_value]."""
        dp_len = len(value_bytes)
        header = seq.to_bytes(2, "big")
        dp_data = bytes([dp_id, dp_type]) + dp_len.to_bytes(2, "big") + value_bytes
        return header + dp_data

    async def test_temperature_dp18(self):
        sensor = _make_sensor()
        listener = _TuyaClusterListener(sensor)

        payload = self._make_tuya_frame(_TUYA_DP_TEMPERATURE, 2, (235).to_bytes(4, "big"))
        listener.cluster_command(0, 0x02, payload)

        assert sensor._last_reading["temperature"] == 23.5
        assert sensor._data_event.is_set()

    async def test_humidity_dp19(self):
        sensor = _make_sensor()
        listener = _TuyaClusterListener(sensor)

        payload = self._make_tuya_frame(_TUYA_DP_HUMIDITY, 2, (65).to_bytes(4, "big"))
        listener.cluster_command(0, 0x02, payload)

        assert sensor._last_reading["humidity"] == 65.0

    async def test_battery_dp21(self):
        sensor = _make_sensor()
        listener = _TuyaClusterListener(sensor)

        payload = self._make_tuya_frame(_TUYA_DP_BATTERY, 2, (90).to_bytes(4, "big"))
        listener.cluster_command(0, 0x02, payload)

        assert sensor._last_reading["sensor_battery"] == 90

    async def test_alternative_dp_ids(self):
        sensor = _make_sensor()
        listener = _TuyaClusterListener(sensor)

        temp = self._make_tuya_frame(_TUYA_DP_TEMPERATURE_ALT, 2, (210).to_bytes(4, "big"))
        hum = self._make_tuya_frame(_TUYA_DP_HUMIDITY_ALT, 2, (72).to_bytes(4, "big"))

        listener.cluster_command(0, 0x02, temp)
        listener.cluster_command(0, 0x02, hum)

        assert sensor._last_reading["temperature"] == 21.0
        assert sensor._last_reading["humidity"] == 72.0

    async def test_multiple_dps_in_single_payload(self):
        sensor = _make_sensor()
        listener = _TuyaClusterListener(sensor)

        header = b"\x00\x01"
        temp_dp = bytes([_TUYA_DP_TEMPERATURE, 2]) + (4).to_bytes(2, "big") + (195).to_bytes(4, "big")
        hum_dp = bytes([_TUYA_DP_HUMIDITY, 2]) + (4).to_bytes(2, "big") + (55).to_bytes(4, "big")
        listener.cluster_command(0, 0x02, header + temp_dp + hum_dp)

        assert sensor._last_reading["temperature"] == 19.5
        assert sensor._last_reading["humidity"] == 55.0

    async def test_negative_temperature(self):
        sensor = _make_sensor()
        listener = _TuyaClusterListener(sensor)

        payload = self._make_tuya_frame(_TUYA_DP_TEMPERATURE, 2, (-50).to_bytes(4, "big", signed=True))
        listener.cluster_command(0, 0x02, payload)

        assert sensor._last_reading["temperature"] == -5.0

    async def test_args_as_list(self):
        sensor = _make_sensor()
        listener = _TuyaClusterListener(sensor)

        payload = self._make_tuya_frame(_TUYA_DP_TEMPERATURE, 2, (250).to_bytes(4, "big"))
        listener.cluster_command(0, 0x02, [payload])

        assert sensor._last_reading["temperature"] == 25.0

    async def test_no_header_payload(self):
        sensor = _make_sensor()
        listener = _TuyaClusterListener(sensor)

        dp_data = bytes([_TUYA_DP_TEMPERATURE, 2]) + (4).to_bytes(2, "big") + (220).to_bytes(4, "big")
        listener.cluster_command(0, 0x02, dp_data)

        assert sensor._last_reading["temperature"] == 22.0

    async def test_ignores_unknown_dp(self):
        sensor = _make_sensor()
        listener = _TuyaClusterListener(sensor)

        payload = self._make_tuya_frame(99, 2, (42).to_bytes(4, "big"))
        listener.cluster_command(0, 0x02, payload)

        assert "temperature" not in sensor._last_reading

    async def test_truncated_payload_doesnt_crash(self):
        sensor = _make_sensor()
        listener = _TuyaClusterListener(sensor)

        listener.cluster_command(0, 0x02, b"\x00\x01\x12")
        assert sensor._last_reading == {}

    async def test_mcu_version_triggers_dp_query(self):
        """MCU version report (cmd 0x11) should opportunistically send a DP query."""
        sensor = _make_sensor()
        mock_cluster = AsyncMock()
        listener = _TuyaClusterListener(sensor, cluster=mock_cluster)

        # cmd 0x11 = MCU version report
        listener.cluster_command(0, 0x11, b"\x00\x03\x40")
        await asyncio.sleep(0.1)

        # Should have sent a DP query (cmd 0x03) with expect_reply=False
        assert mock_cluster.request.call_count >= 1
        call_args = mock_cluster.request.call_args
        assert call_args[0][1] == 0x03  # command_id = DP query
        assert call_args[1].get("expect_reply") is False

    async def test_non_dp_commands_dont_parse_as_dps(self):
        """Non-DP commands (0x11, 0x24) should not try to parse DPs."""
        sensor = _make_sensor()
        listener = _TuyaClusterListener(sensor)

        # MCU version (cmd 0x11) - should not attempt DP parse
        listener.cluster_command(0, 0x11, b"\x00\x03\x40")
        assert sensor._last_reading == {}

    async def test_time_sync_sends_response(self):
        """Time sync request (cmd 0x24) should trigger a time response with expect_reply=False."""
        sensor = _make_sensor()
        mock_cluster = AsyncMock()
        listener = _TuyaClusterListener(sensor, cluster=mock_cluster)

        listener.cluster_command(0, 0x24, b"\x00\x01")
        await asyncio.sleep(0.1)

        # Expect time sync response + opportunistic DP query
        assert mock_cluster.request.call_count >= 1
        # Find the time sync call (cmd 0x24)
        time_sync_calls = [c for c in mock_cluster.request.call_args_list if c[0][1] == 0x24]
        assert len(time_sync_calls) == 1
        assert time_sync_calls[0][1].get("expect_reply") is False

    async def test_dp_query_uses_expect_reply_false(self):
        """DP query must use expect_reply=False for sleepy end devices."""
        sensor = _make_sensor()
        mock_cluster = AsyncMock()
        listener = _TuyaClusterListener(sensor, cluster=mock_cluster)

        await listener._query_dp_values()

        mock_cluster.request.assert_called_once()
        call_args = mock_cluster.request.call_args
        assert call_args[0][1] == 0x03
        assert call_args[1].get("expect_reply") is False

    async def test_opportunistic_query_on_each_command(self):
        """Any incoming command should trigger a DP query if data is incomplete."""
        sensor = _make_sensor()
        mock_cluster = AsyncMock()
        listener = _TuyaClusterListener(sensor, cluster=mock_cluster)

        # First command triggers a DP query
        listener.cluster_command(0, 0x11, b"\x00\x03\x40")
        await asyncio.sleep(0.1)
        assert mock_cluster.request.call_count >= 1

        # Simulate receiving temperature (partial data)
        payload = self._make_tuya_frame(_TUYA_DP_TEMPERATURE, 2, (235).to_bytes(4, "big"))
        mock_cluster.request.reset_mock()
        listener.cluster_command(0, 0x02, payload)
        await asyncio.sleep(0.1)

        # Should query again because humidity is still missing
        assert mock_cluster.request.call_count >= 1

    async def test_no_query_after_complete_data(self):
        """No DP query once both temperature and humidity are received."""
        sensor = _make_sensor()
        mock_cluster = AsyncMock()
        listener = _TuyaClusterListener(sensor, cluster=mock_cluster)

        # Receive both temperature and humidity
        listener._apply_dp(18, 235)
        listener._apply_dp(19, 65)
        assert listener._data_received is True

        mock_cluster.request.reset_mock()
        # Another command should NOT trigger a DP query
        listener.cluster_command(0, 0x11, b"\x00\x03\x40")
        await asyncio.sleep(0.1)
        mock_cluster.request.assert_not_called()


@pytest.mark.asyncio
class TestInstallTuyaListener:
    """Tests that _install_listeners_for_device installs Tuya listener on 0xEF00."""

    async def test_installs_tuya_listener_on_ef00(self):
        sensor = _make_sensor()

        mock_tuya_cluster = MagicMock()
        mock_endpoint = MagicMock()
        mock_endpoint.in_clusters = {_CLUSTER_TUYA: mock_tuya_cluster}

        mock_device = MagicMock()
        mock_device.endpoints = {0: MagicMock(), 1: mock_endpoint}

        sensor._install_listeners_for_device(mock_device)

        mock_tuya_cluster.add_listener.assert_called_once()
        listener_arg = mock_tuya_cluster.add_listener.call_args[0][0]
        assert isinstance(listener_arg, _TuyaClusterListener)

    async def test_installs_both_standard_and_tuya(self):
        """Device with both standard and Tuya clusters gets both listeners."""
        sensor = _make_sensor()

        mock_temp_cluster = MagicMock()
        mock_tuya_cluster = MagicMock()
        mock_endpoint = MagicMock()
        mock_endpoint.in_clusters = {
            _CLUSTER_TEMPERATURE: mock_temp_cluster,
            _CLUSTER_TUYA: mock_tuya_cluster,
        }

        mock_device = MagicMock()
        mock_device.endpoints = {0: MagicMock(), 1: mock_endpoint}

        sensor._install_listeners_for_device(mock_device)

        mock_temp_cluster.add_listener.assert_called_once()
        mock_tuya_cluster.add_listener.assert_called_once()
