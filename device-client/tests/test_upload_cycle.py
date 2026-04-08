from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from bugsi_daemon.buffer.backup import BufferBackup
from bugsi_daemon.config import ConfigManager
from bugsi_daemon.core.power_manager import PowerManager, PowerMode
from bugsi_daemon.core.telemetry_collector import TelemetryCollector
from bugsi_daemon.core.upload_cycle import UploadCycle
from bugsi_daemon.hardware_mock.climate import MockClimate
from bugsi_daemon.hardware_mock.wlan import MockWlan
from bugsi_daemon.net.client import BugsiClient


@pytest.mark.asyncio
class TestUploadCycle:
    async def _setup(self, buffer_store, mock_hardware, config_manager, tmp_path):
        for sensor in mock_hardware.values():
            if hasattr(sensor, "initialize"):
                await sensor.initialize()

        client = BugsiClient(config_manager.api_url, config_manager.api_key)
        backup = BufferBackup(str(tmp_path / "buffer.db"), str(tmp_path / "backup"))

        telemetry = TelemetryCollector(
            buffer=buffer_store,
            battery=mock_hardware["battery"],
            solar=mock_hardware["solar"],
            climate=mock_hardware["climate"],
            storage=mock_hardware["storage"],
            system=mock_hardware["system"],
            lte=mock_hardware["lte"],
        )

        power_manager = PowerManager(
            config=config_manager,
            lte=mock_hardware["lte"],
            power_mgmt=mock_hardware["power_mgmt"],
            backup=backup,
        )

        upload = UploadCycle(
            client=client,
            buffer=buffer_store,
            config=config_manager,
            power_manager=power_manager,
            telemetry_collector=telemetry,
        )

        return upload, client, telemetry

    @respx.mock
    async def test_upload_sends_pending_telemetry(self, buffer_store, mock_hardware, config_manager, tmp_path):
        upload, client, telemetry = await self._setup(buffer_store, mock_hardware, config_manager, tmp_path)

        # Push some telemetry to buffer
        await buffer_store.push_telemetry({"timestamp": "2026-03-07T12:00:00Z", "battery_soc": 75.0})

        # Mock API endpoints
        tel_route = respx.post("http://test:8000/api/device-data/telemetry").mock(
            return_value=httpx.Response(201, json=[{"id": "abc"}])
        )
        config_route = respx.get("http://test:8000/api/device-data/config").mock(
            return_value=httpx.Response(200, json={"version": 1, "config": {}, "has_update": False})
        )

        success = await upload.run(last_battery_soc=80.0)
        assert success
        assert tel_route.called

        # Buffer should be empty now
        pending = await buffer_store.get_pending_telemetry()
        assert len(pending) == 0

        client.close()

    @respx.mock
    async def test_upload_skipped_low_battery(self, buffer_store, mock_hardware, config_manager, tmp_path):
        upload, client, telemetry = await self._setup(buffer_store, mock_hardware, config_manager, tmp_path)

        await buffer_store.push_telemetry({"timestamp": "2026-03-07T12:00:00Z", "battery_soc": 15.0})

        success = await upload.run(last_battery_soc=15.0)
        assert not success

        # Buffer should still have data
        pending = await buffer_store.get_pending_telemetry()
        assert len(pending) == 1

        client.close()

    @respx.mock
    async def test_upload_polls_config(self, buffer_store, mock_hardware, config_manager, tmp_path):
        upload, client, telemetry = await self._setup(buffer_store, mock_hardware, config_manager, tmp_path)

        respx.post("http://test:8000/api/device-data/telemetry").mock(
            return_value=httpx.Response(201, json=[])
        )
        respx.get("http://test:8000/api/device-data/config").mock(
            return_value=httpx.Response(200, json={
                "version": 5,
                "config": {"upload": {"interval_minutes": 30}},
                "has_update": True,
            })
        )
        ack_route = respx.post("http://test:8000/api/device-data/config/ack").mock(
            return_value=httpx.Response(204)
        )

        await upload.run(last_battery_soc=80.0)

        assert ack_route.called
        assert config_manager.get("upload.interval_minutes") == 30
        assert config_manager.version == 5

        client.close()

    @respx.mock
    async def test_config_polled_after_telemetry_and_thumbnail(self, buffer_store, mock_hardware, config_manager, tmp_path):
        """Config is polled after telemetry upload and again after thumbnail upload."""
        upload, client, telemetry = await self._setup(buffer_store, mock_hardware, config_manager, tmp_path)

        await buffer_store.push_telemetry({"timestamp": "2026-03-07T12:00:00Z", "battery_soc": 75.0})

        respx.post("http://test:8000/api/device-data/telemetry").mock(
            return_value=httpx.Response(201, json=[{"id": "abc"}])
        )
        config_route = respx.get("http://test:8000/api/device-data/config").mock(
            return_value=httpx.Response(200, json={"version": 1, "config": {}, "has_update": False})
        )

        await upload.run(last_battery_soc=80.0)

        # Config should be polled twice: once after telemetry, once after thumbnail
        assert config_route.call_count == 2

        client.close()

    @respx.mock
    async def test_upload_error_does_not_lose_data(self, buffer_store, mock_hardware, config_manager, tmp_path):
        upload, client, telemetry = await self._setup(buffer_store, mock_hardware, config_manager, tmp_path)

        await buffer_store.push_telemetry({"timestamp": "2026-03-07T12:00:00Z", "battery_soc": 75.0})

        # Simulate server error
        respx.post("http://test:8000/api/device-data/telemetry").mock(
            return_value=httpx.Response(500, json={"detail": "Internal error"})
        )
        respx.get("http://test:8000/api/device-data/config").mock(
            return_value=httpx.Response(200, json={"version": 1, "config": {}, "has_update": False})
        )

        await upload.run(last_battery_soc=80.0)

        # Data should still be in buffer
        pending = await buffer_store.get_pending_telemetry()
        assert len(pending) == 1

        client.close()

    @respx.mock
    async def test_upload_uses_wlan_when_internet_available(self, buffer_store, mock_hardware, config_manager, tmp_path):
        """When WLAN has internet, upload should skip LTE entirely."""
        for sensor in mock_hardware.values():
            if hasattr(sensor, "initialize"):
                await sensor.initialize()

        wlan = MockWlan(has_internet=True)
        client = BugsiClient(config_manager.api_url, config_manager.api_key)
        backup = BufferBackup(str(tmp_path / "buffer.db"), str(tmp_path / "backup"))

        telemetry = TelemetryCollector(
            buffer=buffer_store,
            battery=mock_hardware["battery"],
            solar=mock_hardware["solar"],
            climate=mock_hardware["climate"],
            storage=mock_hardware["storage"],
            system=mock_hardware["system"],
            lte=mock_hardware["lte"],
        )

        power_manager = PowerManager(
            config=config_manager,
            lte=mock_hardware["lte"],
            power_mgmt=mock_hardware["power_mgmt"],
            backup=backup,
        )

        upload = UploadCycle(
            client=client,
            buffer=buffer_store,
            config=config_manager,
            power_manager=power_manager,
            telemetry_collector=telemetry,
            wlan=wlan,
        )

        await buffer_store.push_telemetry({"timestamp": "2026-03-07T12:00:00Z", "battery_soc": 75.0})

        respx.post("http://test:8000/api/device-data/telemetry").mock(
            return_value=httpx.Response(201, json=[{"id": "abc"}])
        )
        respx.get("http://test:8000/api/device-data/config").mock(
            return_value=httpx.Response(200, json={"version": 1, "config": {}, "has_update": False})
        )

        success = await upload.run(last_battery_soc=80.0)
        assert success

        # LTE should never have been powered on
        assert not mock_hardware["lte"].is_powered()

        client.close()

    @respx.mock
    async def test_upload_falls_back_to_lte_when_no_wlan_internet(self, buffer_store, mock_hardware, config_manager, tmp_path):
        """When WLAN has no internet, upload should use LTE as before."""
        for sensor in mock_hardware.values():
            if hasattr(sensor, "initialize"):
                await sensor.initialize()

        wlan = MockWlan(has_internet=False)
        client = BugsiClient(config_manager.api_url, config_manager.api_key)
        backup = BufferBackup(str(tmp_path / "buffer.db"), str(tmp_path / "backup"))

        telemetry = TelemetryCollector(
            buffer=buffer_store,
            battery=mock_hardware["battery"],
            solar=mock_hardware["solar"],
            climate=mock_hardware["climate"],
            storage=mock_hardware["storage"],
            system=mock_hardware["system"],
            lte=mock_hardware["lte"],
        )

        power_manager = PowerManager(
            config=config_manager,
            lte=mock_hardware["lte"],
            power_mgmt=mock_hardware["power_mgmt"],
            backup=backup,
        )

        upload = UploadCycle(
            client=client,
            buffer=buffer_store,
            config=config_manager,
            power_manager=power_manager,
            telemetry_collector=telemetry,
            wlan=wlan,
        )

        await buffer_store.push_telemetry({"timestamp": "2026-03-07T12:00:00Z", "battery_soc": 75.0})

        respx.post("http://test:8000/api/device-data/telemetry").mock(
            return_value=httpx.Response(201, json=[{"id": "abc"}])
        )
        respx.get("http://test:8000/api/device-data/config").mock(
            return_value=httpx.Response(200, json={"version": 1, "config": {}, "has_update": False})
        )

        success = await upload.run(last_battery_soc=80.0)
        assert success

        # LTE should have been powered on (then off in finally)
        assert not mock_hardware["lte"].is_powered()

        client.close()


@pytest.mark.asyncio
class TestUploadCycleApMode:
    """Tests for upload behaviour when the WiFi hotspot is active."""

    async def _make_upload(self, buffer_store, mock_hardware, config_manager, tmp_path, wlan):
        for sensor in mock_hardware.values():
            if hasattr(sensor, "initialize"):
                await sensor.initialize()

        client = BugsiClient(config_manager.api_url, config_manager.api_key)
        backup = BufferBackup(str(tmp_path / "buffer.db"), str(tmp_path / "backup"))

        telemetry = TelemetryCollector(
            buffer=buffer_store,
            battery=mock_hardware["battery"],
            solar=mock_hardware["solar"],
            climate=mock_hardware["climate"],
            storage=mock_hardware["storage"],
            system=mock_hardware["system"],
            lte=mock_hardware["lte"],
        )

        power_manager = PowerManager(
            config=config_manager,
            lte=mock_hardware["lte"],
            power_mgmt=mock_hardware["power_mgmt"],
            backup=backup,
        )

        upload = UploadCycle(
            client=client,
            buffer=buffer_store,
            config=config_manager,
            power_manager=power_manager,
            telemetry_collector=telemetry,
            wlan=wlan,
        )
        return upload, client

    @respx.mock
    async def test_hotspot_active_server_reachable_skips_lte(
        self, buffer_store, mock_hardware, config_manager, tmp_path
    ):
        """When hotspot is active and server is reachable on AP network, skip LTE."""
        wlan = MockWlan(has_internet=False, server_reachable=True)
        await wlan.start_hotspot("BUGSI-Setup", "bugsi1234")

        upload, client = await self._make_upload(
            buffer_store, mock_hardware, config_manager, tmp_path, wlan
        )

        await buffer_store.push_telemetry(
            {"timestamp": "2026-03-07T12:00:00Z", "battery_soc": 75.0}
        )

        respx.post("http://test:8000/api/device-data/telemetry").mock(
            return_value=httpx.Response(201, json=[{"id": "abc"}])
        )
        respx.get("http://test:8000/api/device-data/config").mock(
            return_value=httpx.Response(
                200, json={"version": 1, "config": {}, "has_update": False}
            )
        )

        success = await upload.run(last_battery_soc=80.0)
        assert success

        # LTE should never have been powered on
        assert not mock_hardware["lte"].is_powered()

        client.close()

    @respx.mock
    async def test_hotspot_active_server_not_reachable_uses_lte(
        self, buffer_store, mock_hardware, config_manager, tmp_path
    ):
        """When hotspot is active but server unreachable, use LTE with routing fix."""
        wlan = MockWlan(has_internet=False, server_reachable=False)
        await wlan.start_hotspot("BUGSI-Setup", "bugsi1234")

        upload, client = await self._make_upload(
            buffer_store, mock_hardware, config_manager, tmp_path, wlan
        )

        await buffer_store.push_telemetry(
            {"timestamp": "2026-03-07T12:00:00Z", "battery_soc": 75.0}
        )

        respx.post("http://test:8000/api/device-data/telemetry").mock(
            return_value=httpx.Response(201, json=[{"id": "abc"}])
        )
        respx.get("http://test:8000/api/device-data/config").mock(
            return_value=httpx.Response(
                200, json={"version": 1, "config": {}, "has_update": False}
            )
        )

        route_enter = AsyncMock(return_value=None)
        route_exit = AsyncMock(return_value=None)

        with patch(
            "bugsi_daemon.core.upload_cycle.LteRoute"
        ) as MockRoute, patch(
            "bugsi_daemon.core.upload_cycle.resolve_ip", return_value="10.0.0.1"
        ):
            mock_route_inst = MockRoute.return_value
            mock_route_inst.__aenter__ = route_enter
            mock_route_inst.__aexit__ = route_exit

            success = await upload.run(last_battery_soc=80.0)

        assert success

        # LTE should have been powered on (then off in finally)
        assert not mock_hardware["lte"].is_powered()

        # Route context manager should have been used
        MockRoute.assert_called_once_with("10.0.0.1", "usb0")
        route_enter.assert_awaited_once()
        route_exit.assert_awaited_once()

        client.close()

    @respx.mock
    async def test_hotspot_active_lte_registration_fails(
        self, buffer_store, mock_hardware, config_manager, tmp_path
    ):
        """When hotspot is active, server unreachable, and LTE registration fails."""
        wlan = MockWlan(has_internet=False, server_reachable=False)
        await wlan.start_hotspot("BUGSI-Setup", "bugsi1234")

        # Make LTE fail registration
        mock_hardware["lte"].wait_for_network = AsyncMock(return_value=False)

        upload, client = await self._make_upload(
            buffer_store, mock_hardware, config_manager, tmp_path, wlan
        )

        success = await upload.run(last_battery_soc=80.0)
        assert not success

        client.close()


@pytest.mark.asyncio
class TestTelemetryClimatePower:
    """Tests for climate sensor power management during telemetry collection."""

    async def test_telemetry_powers_on_climate_for_reading(self, buffer_store, mock_hardware, config_manager):
        """Climate sensor should be powered on before reading and powered off after."""
        for sensor in mock_hardware.values():
            if hasattr(sensor, "initialize"):
                await sensor.initialize()

        climate = mock_hardware["climate"]
        # Simulate climate being powered off (e.g. after image pipeline capture)
        await climate.power_off()
        assert not climate.is_powered()
        assert not climate.is_healthy()

        telemetry = TelemetryCollector(
            buffer=buffer_store,
            battery=mock_hardware["battery"],
            solar=mock_hardware["solar"],
            climate=climate,
            storage=mock_hardware["storage"],
            system=mock_hardware["system"],
            lte=mock_hardware["lte"],
        )

        reading = await telemetry.collect()

        # Temperature and humidity should be present
        assert "temperature" in reading
        assert "humidity" in reading
        assert reading["temperature"] is not None
        assert reading["humidity"] is not None

        # Climate should be powered off again after collection
        assert not climate.is_powered()

    async def test_telemetry_skips_power_if_already_powered(self, buffer_store, mock_hardware, config_manager):
        """If climate is already powered, don't power off after reading."""
        for sensor in mock_hardware.values():
            if hasattr(sensor, "initialize"):
                await sensor.initialize()

        climate = mock_hardware["climate"]
        # Climate is already powered after initialize()
        assert climate.is_powered()

        telemetry = TelemetryCollector(
            buffer=buffer_store,
            battery=mock_hardware["battery"],
            solar=mock_hardware["solar"],
            climate=climate,
            storage=mock_hardware["storage"],
            system=mock_hardware["system"],
            lte=mock_hardware["lte"],
        )

        reading = await telemetry.collect()

        assert "temperature" in reading
        assert "humidity" in reading
        # Should still be powered (we didn't power it on, so we don't power it off)
        assert climate.is_powered()

    async def test_telemetry_climate_failure_does_not_crash(self, buffer_store, mock_hardware, config_manager):
        """Other telemetry should still be collected if climate sensor fails."""
        for sensor in mock_hardware.values():
            if hasattr(sensor, "initialize"):
                await sensor.initialize()

        # Use a climate sensor that raises on power_on
        class FailingClimate(MockClimate):
            async def power_on(self):
                raise RuntimeError("USB dongle not found")

        climate = FailingClimate()
        # Don't initialize — stays unhealthy/unpowered

        telemetry = TelemetryCollector(
            buffer=buffer_store,
            battery=mock_hardware["battery"],
            solar=mock_hardware["solar"],
            climate=climate,
            storage=mock_hardware["storage"],
            system=mock_hardware["system"],
            lte=mock_hardware["lte"],
        )

        reading = await telemetry.collect()

        # Climate data should be missing, but other data should be present
        assert "temperature" not in reading
        assert "battery_voltage" in reading
        assert "timestamp" in reading
