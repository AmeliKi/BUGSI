import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bugsi_daemon.hardware.climate import ZigbeeClimateSensor


def _make_sensor(**kwargs) -> ZigbeeClimateSensor:
    defaults = {"serial_port": "auto", "adapter": "ezsp"}
    defaults.update(kwargs)
    return ZigbeeClimateSensor(**defaults)


def _make_mock_app(devices=None):
    """Create a mock zigpy ControllerApplication."""
    app = AsyncMock()
    app.devices = devices or {}
    app.permit = AsyncMock()
    app.add_listener = MagicMock()
    app.remove_listener = MagicMock()
    return app


@pytest.mark.asyncio
class TestPairZigbee:
    async def test_not_powered_raises(self):
        sensor = _make_sensor()
        with pytest.raises(RuntimeError, match="powered on"):
            await sensor.pair_zigbee()

    async def test_calls_permit_on_app(self):
        sensor = _make_sensor()
        sensor._powered = True
        sensor._app = _make_mock_app()

        # Make permit_join timeout immediately
        with patch("asyncio.timeout", side_effect=asyncio.TimeoutError):
            await sensor.pair_zigbee(timeout=1)

        # Verify permit was called with timeout
        sensor._app.permit.assert_any_call(time_s=1)

    async def test_collects_joined_devices(self):
        sensor = _make_sensor()
        sensor._powered = True

        mock_app = _make_mock_app()

        # Capture the listener when add_listener is called, then simulate a join
        captured_listener = None

        def capture_and_trigger(listener):
            nonlocal captured_listener
            captured_listener = listener
            # Simulate device join after listener is registered
            mock_device = MagicMock()
            mock_device.ieee = "0xaabbccdd"
            mock_device.model = "ZTH01"
            mock_device.manufacturer = "Tuya"
            mock_device.endpoints = {}
            mock_app.devices = {mock_device.ieee: mock_device}
            listener.device_joined(mock_device)

        mock_app.add_listener.side_effect = capture_and_trigger
        sensor._app = mock_app

        joined = await sensor.pair_zigbee(timeout=1)

        assert len(joined) == 1
        assert joined[0]["ieee_address"] == "0xaabbccdd"
        assert joined[0]["model"] == "ZTH01"

    async def test_callback_called(self):
        sensor = _make_sensor()
        sensor._powered = True

        mock_app = _make_mock_app()
        callback_args = []

        def capture_and_trigger(listener):
            mock_device = MagicMock()
            mock_device.ieee = "0xaabb"
            mock_device.model = None
            mock_device.manufacturer = None
            mock_device.endpoints = {}
            mock_app.devices = {mock_device.ieee: mock_device}
            listener.device_joined(mock_device)

        mock_app.add_listener.side_effect = capture_and_trigger
        sensor._app = mock_app

        joined = await sensor.pair_zigbee(
            timeout=1,
            on_device_joined=lambda d: callback_args.append(d),
        )

        assert len(callback_args) == 1
        assert callback_args[0]["friendly_name"] == "0xaabb"

    async def test_disables_permit_after(self):
        sensor = _make_sensor()
        sensor._powered = True
        sensor._app = _make_mock_app()

        with patch("asyncio.timeout", side_effect=asyncio.TimeoutError):
            await sensor.pair_zigbee(timeout=1)

        # Last permit call should disable pairing
        calls = sensor._app.permit.call_args_list
        assert len(calls) >= 2
        assert calls[-1].kwargs.get("time_s") == 0 or calls[-1].args == (0,) or \
            calls[-1] == ({"time_s": 0},)


@pytest.mark.asyncio
class TestRenameDevice:
    async def test_not_powered_raises(self):
        sensor = _make_sensor()
        with pytest.raises(RuntimeError, match="powered on"):
            await sensor.rename_device("old", "new")

    async def test_success(self, tmp_path):
        import bugsi_daemon.hardware.climate as climate_mod
        name_file = tmp_path / "zigbee_names.json"
        name_file.write_text(json.dumps({"0xaabb": "old_name"}))
        original = climate_mod._NAME_MAP_PATH
        climate_mod._NAME_MAP_PATH = name_file

        try:
            sensor = _make_sensor()
            sensor._powered = True
            sensor._app = _make_mock_app()

            result = await sensor.rename_device("old_name", "new_name")
            assert result is True

            # Verify the file was updated
            data = json.loads(name_file.read_text())
            assert data["0xaabb"] == "new_name"
        finally:
            climate_mod._NAME_MAP_PATH = original

    async def test_unknown_name_returns_false(self, tmp_path):
        import bugsi_daemon.hardware.climate as climate_mod
        name_file = tmp_path / "zigbee_names.json"
        name_file.write_text(json.dumps({}))
        original = climate_mod._NAME_MAP_PATH
        climate_mod._NAME_MAP_PATH = name_file

        try:
            sensor = _make_sensor()
            sensor._powered = True
            sensor._app = _make_mock_app()

            result = await sensor.rename_device("nonexistent", "new_name")
            assert result is False
        finally:
            climate_mod._NAME_MAP_PATH = original

    async def test_timeout(self):
        """Rename returns False when name not found (replaces old MQTT timeout test)."""
        sensor = _make_sensor()
        sensor._powered = True
        sensor._app = _make_mock_app()

        # With empty name map, rename should fail
        with patch.object(ZigbeeClimateSensor, "_load_name_map", return_value={}):
            result = await sensor.rename_device("old_name", "new_name")

        assert result is False
