import httpx
import pytest
import respx

from bugsi_daemon.buffer.backup import BufferBackup
from bugsi_daemon.config import ConfigManager
from bugsi_daemon.core.power_manager import PowerManager, PowerMode
from bugsi_daemon.core.telemetry_collector import TelemetryCollector
from bugsi_daemon.core.upload_cycle import UploadCycle
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
