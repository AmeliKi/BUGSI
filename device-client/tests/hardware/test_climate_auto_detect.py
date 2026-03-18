import asyncio
import json
from unittest.mock import AsyncMock, patch, call

import pytest

from bugsi_daemon.hardware.climate import ZigbeeClimateSensor


UHUBCTL_OUTPUT_SONOFF = """\
Current status for hub 1 [1d6b:0002 Linux 6.12.47+rpt-rpi-2712 xhci-hcd xHCI Host Controller xhci-hcd.0, USB 2.00, 2 ports, ppps]
  Port 1: 0103 power enable connect [10c4:ea60 Itead Sonoff Zigbee 3.0 USB Dongle Plus V2 fcc2f7e3e3f3ef11adedc41b6d9880ab]
  Port 2: 0100 power
"""

UHUBCTL_OUTPUT_MULTI_HUB = """\
Current status for hub 1-1 [1d6b:0002 Linux root hub, USB 2.00, 4 ports, ppps]
  Port 1: 0100 power
  Port 2: 0100 power
  Port 3: 0100 power
  Port 4: 0100 power
Current status for hub 2 [1d6b:0002 Linux root hub, USB 2.00, 2 ports, ppps]
  Port 1: 0100 power
  Port 2: 0103 power enable connect [1a86:55d4 Some Zigbee Coordinator]
"""

UHUBCTL_OUTPUT_NO_ZIGBEE = """\
Current status for hub 1 [1d6b:0002 Linux root hub, USB 2.00, 2 ports, ppps]
  Port 1: 0103 power enable connect [046d:c52b Logitech USB Receiver]
  Port 2: 0100 power
Current status for hub 2 [1d6b:0002 Linux root hub, USB 2.00, 1 port, ppps]
  Port 1: 0100 power
"""


def _make_sensor(**kwargs) -> ZigbeeClimateSensor:
    """Create a sensor without triggering MQTT (we only test USB detection)."""
    return ZigbeeClimateSensor(**kwargs)


def _mock_subprocess(stdout: str, returncode: int = 0):
    """Return an AsyncMock that mimics asyncio.create_subprocess_exec for uhubctl."""
    proc = AsyncMock()
    proc.communicate.return_value = (stdout.encode(), b"")
    proc.returncode = returncode
    mock = AsyncMock(return_value=proc)
    return mock


@pytest.mark.asyncio
class TestParseUhubctlOutput:
    async def test_parse_single_hub_with_dongle(self):
        sensor = _make_sensor()
        hubs, hub, port = await sensor._parse_uhubctl_output(UHUBCTL_OUTPUT_SONOFF)
        assert hubs == ["1"]
        assert hub == "1"
        assert port == "1"

    async def test_parse_multi_hub(self):
        sensor = _make_sensor()
        hubs, hub, port = await sensor._parse_uhubctl_output(UHUBCTL_OUTPUT_MULTI_HUB)
        assert hubs == ["1-1", "2"]
        assert hub == "2"
        assert port == "2"

    async def test_parse_no_zigbee(self):
        sensor = _make_sensor()
        hubs, hub, port = await sensor._parse_uhubctl_output(UHUBCTL_OUTPUT_NO_ZIGBEE)
        assert hubs == ["1", "2"]
        assert hub is None
        assert port is None


@pytest.mark.asyncio
class TestAutoDetectZigbeeUsb:
    async def test_detects_sonoff_dongle(self):
        sensor = _make_sensor()
        assert sensor._usb_hub is None
        assert sensor._usb_port is None

        with patch("asyncio.create_subprocess_exec", _mock_subprocess(UHUBCTL_OUTPUT_SONOFF)):
            with patch.object(type(sensor), "_save_usb_cache"):
                await sensor._auto_detect_zigbee_usb()

        assert sensor._usb_hub == "1"
        assert sensor._usb_port == "1"

    async def test_detects_dongle_on_second_hub(self):
        sensor = _make_sensor()

        with patch("asyncio.create_subprocess_exec", _mock_subprocess(UHUBCTL_OUTPUT_MULTI_HUB)):
            with patch.object(type(sensor), "_save_usb_cache"):
                await sensor._auto_detect_zigbee_usb()

        assert sensor._usb_hub == "2"
        assert sensor._usb_port == "2"

    async def test_no_zigbee_dongle_found(self):
        sensor = _make_sensor()

        with patch("asyncio.create_subprocess_exec", _mock_subprocess(UHUBCTL_OUTPUT_NO_ZIGBEE)):
            await sensor._auto_detect_zigbee_usb()

        assert sensor._usb_hub is None
        assert sensor._usb_port is None

    async def test_uhubctl_not_installed(self):
        sensor = _make_sensor()

        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
            await sensor._auto_detect_zigbee_usb()

        assert sensor._usb_hub is None
        assert sensor._usb_port is None

    async def test_uhubctl_failure(self):
        sensor = _make_sensor()

        with patch("asyncio.create_subprocess_exec", _mock_subprocess("", returncode=1)):
            await sensor._auto_detect_zigbee_usb()

        assert sensor._usb_hub is None
        assert sensor._usb_port is None


@pytest.mark.asyncio
class TestUhubctlPower:
    async def test_skips_detection_when_configured(self):
        sensor = _make_sensor(usb_hub="3", usb_port="2")

        with patch.object(sensor, "_auto_detect_zigbee_usb") as mock_detect:
            with patch("asyncio.create_subprocess_exec", _mock_subprocess("", returncode=0)):
                await sensor._uhubctl_power("on")

        mock_detect.assert_not_called()

    async def test_uses_configured_hub_port(self):
        sensor = _make_sensor(usb_hub="1", usb_port="1")

        mock = _mock_subprocess("", returncode=0)
        with patch("asyncio.create_subprocess_exec", mock):
            await sensor._uhubctl_power("on")

        mock.assert_called_once_with(
            "uhubctl", "-a", "on", "-l", "1", "-p", "1",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    async def test_uses_cached_hub_port_when_dongle_off(self):
        """When auto-detect fails but cache exists, use cached values."""
        sensor = _make_sensor()

        with patch.object(sensor, "_auto_detect_zigbee_usb", AsyncMock()):
            with patch.object(type(sensor), "_load_usb_cache", return_value=("1", "1")):
                with patch("asyncio.create_subprocess_exec", _mock_subprocess("", returncode=0)) as mock:
                    await sensor._uhubctl_power("on")

        assert sensor._usb_hub == "1"
        assert sensor._usb_port == "1"
        mock.assert_called_once_with(
            "uhubctl", "-a", "on", "-l", "1", "-p", "1",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    async def test_falls_back_to_all_hubs_when_no_cache(self):
        """When auto-detect fails and no cache, power on each hub individually."""
        sensor = _make_sensor()

        with patch.object(sensor, "_auto_detect_zigbee_usb", AsyncMock()):
            with patch.object(type(sensor), "_load_usb_cache", return_value=(None, None)):
                with patch.object(sensor, "_uhubctl_power_all_hubs", AsyncMock()) as mock_all:
                    await sensor._uhubctl_power("on")

        mock_all.assert_called_once_with("on")

    async def test_re_detects_after_powering_all_hubs_on(self):
        """After powering on all hubs, re-detect so we know which port for power off."""
        sensor = _make_sensor()
        detect_calls = []

        async def track_detect():
            detect_calls.append(1)

        with patch.object(sensor, "_auto_detect_zigbee_usb", side_effect=track_detect):
            with patch.object(type(sensor), "_load_usb_cache", return_value=(None, None)):
                with patch.object(sensor, "_uhubctl_power_all_hubs", AsyncMock()):
                    with patch("asyncio.sleep", AsyncMock()):
                        await sensor._uhubctl_power("on")


@pytest.mark.asyncio
class TestUhubctlPowerAllHubs:
    async def test_powers_each_hub(self):
        sensor = _make_sensor()

        calls = []

        async def mock_exec(*args, **kwargs):
            calls.append(args)
            proc = AsyncMock()
            proc.communicate.return_value = (UHUBCTL_OUTPUT_NO_ZIGBEE.encode(), b"")
            proc.returncode = 0
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=mock_exec):
            await sensor._uhubctl_power_all_hubs("on")

        # First call: uhubctl (enumerate), then one call per hub
        assert len(calls) == 3  # enumerate + hub 1 + hub 2
        assert calls[1] == ("uhubctl", "-a", "on", "-l", "1")
        assert calls[2] == ("uhubctl", "-a", "on", "-l", "2")


@pytest.mark.asyncio
class TestUsbCache:
    async def test_saves_cache_on_detection(self, tmp_path):
        import bugsi_daemon.hardware.climate as climate_mod
        cache_file = tmp_path / "zigbee_usb.json"
        original = climate_mod._USB_CACHE_PATH
        climate_mod._USB_CACHE_PATH = cache_file

        try:
            sensor = _make_sensor()
            with patch("asyncio.create_subprocess_exec", _mock_subprocess(UHUBCTL_OUTPUT_SONOFF)):
                await sensor._auto_detect_zigbee_usb()

            assert cache_file.exists()
            data = json.loads(cache_file.read_text())
            assert data == {"usb_hub": "1", "usb_port": "1"}
        finally:
            climate_mod._USB_CACHE_PATH = original

    async def test_loads_cache(self, tmp_path):
        import bugsi_daemon.hardware.climate as climate_mod
        cache_file = tmp_path / "zigbee_usb.json"
        cache_file.write_text(json.dumps({"usb_hub": "2", "usb_port": "3"}))
        original = climate_mod._USB_CACHE_PATH
        climate_mod._USB_CACHE_PATH = cache_file

        try:
            hub, port = ZigbeeClimateSensor._load_usb_cache()
            assert hub == "2"
            assert port == "3"
        finally:
            climate_mod._USB_CACHE_PATH = original

    async def test_load_cache_missing_file(self, tmp_path):
        import bugsi_daemon.hardware.climate as climate_mod
        original = climate_mod._USB_CACHE_PATH
        climate_mod._USB_CACHE_PATH = tmp_path / "nonexistent.json"

        try:
            hub, port = ZigbeeClimateSensor._load_usb_cache()
            assert hub is None
            assert port is None
        finally:
            climate_mod._USB_CACHE_PATH = original
