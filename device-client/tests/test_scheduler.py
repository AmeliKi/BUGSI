import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from bugsi_daemon.buffer.backup import BufferBackup
from bugsi_daemon.buffer.store import BufferStore
from bugsi_daemon.core.power_manager import PowerManager
from bugsi_daemon.core.scheduler import Scheduler
from bugsi_daemon.core.telemetry_collector import TelemetryCollector
from bugsi_daemon.core.upload_cycle import UploadCycle
from bugsi_daemon.net.client import BugsiClient


@pytest.mark.asyncio
class TestScheduler:
    async def _make_scheduler(self, buffer_store, mock_hardware, config_manager, tmp_path):
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

        scheduler = Scheduler(
            config=config_manager,
            telemetry_collector=telemetry,
            upload_cycle=upload,
            power_manager=power_manager,
            buffer=buffer_store,
            backup=backup,
        )

        return scheduler, client

    async def test_start_and_stop(self, buffer_store, mock_hardware, config_manager, tmp_path):
        scheduler, client = await self._make_scheduler(buffer_store, mock_hardware, config_manager, tmp_path)

        # Start scheduler in background, stop after a short delay
        async def stop_after_delay():
            await asyncio.sleep(0.2)
            await scheduler.stop()

        task = asyncio.create_task(scheduler.start())
        stop_task = asyncio.create_task(stop_after_delay())

        # Wait for both, with a timeout to prevent hanging
        done, pending = await asyncio.wait(
            [task, stop_task],
            timeout=5.0,
        )

        for t in pending:
            t.cancel()

        client.close()

    async def test_telemetry_collected_on_start(self, buffer_store, mock_hardware, config_manager, tmp_path):
        # Set very short interval
        config_manager.apply_remote({"telemetry": {"collection_interval_minutes": 0}}, version=99)

        scheduler, client = await self._make_scheduler(buffer_store, mock_hardware, config_manager, tmp_path)

        async def stop_after_collection():
            # Wait for at least one telemetry collection
            for _ in range(20):
                await asyncio.sleep(0.1)
                pending = await buffer_store.get_pending_telemetry()
                if pending:
                    await scheduler.stop()
                    return
            await scheduler.stop()

        task = asyncio.create_task(scheduler.start())
        stop_task = asyncio.create_task(stop_after_collection())

        await asyncio.wait([task, stop_task], timeout=5.0)

        pending = await buffer_store.get_pending_telemetry()
        assert len(pending) >= 1

        client.close()
