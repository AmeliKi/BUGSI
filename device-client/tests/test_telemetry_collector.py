import pytest

from bugsi_daemon.core.telemetry_collector import TelemetryCollector


@pytest.mark.asyncio
class TestTelemetryCollector:
    async def test_collect_returns_all_fields(self, buffer_store, mock_hardware):
        for sensor in mock_hardware.values():
            if hasattr(sensor, "initialize"):
                await sensor.initialize()

        collector = TelemetryCollector(
            buffer=buffer_store,
            battery=mock_hardware["battery"],
            solar=mock_hardware["solar"],
            climate=mock_hardware["climate"],
            storage=mock_hardware["storage"],
            system=mock_hardware["system"],
            lte=mock_hardware["lte"],
        )

        reading = await collector.collect()

        assert "timestamp" in reading
        assert "battery_voltage" in reading
        assert "battery_soc" in reading
        assert "temperature" in reading
        assert "humidity" in reading
        assert "storage_used_mb" in reading
        assert "storage_total_mb" in reading
        assert "cpu_temp" in reading
        assert "uptime_seconds" in reading

    async def test_collect_pushes_to_buffer(self, buffer_store, mock_hardware):
        for sensor in mock_hardware.values():
            if hasattr(sensor, "initialize"):
                await sensor.initialize()

        collector = TelemetryCollector(
            buffer=buffer_store,
            battery=mock_hardware["battery"],
            solar=mock_hardware["solar"],
            climate=mock_hardware["climate"],
            storage=mock_hardware["storage"],
            system=mock_hardware["system"],
            lte=mock_hardware["lte"],
        )

        await collector.collect()

        pending = await buffer_store.get_pending_telemetry()
        assert len(pending) == 1

    async def test_lte_signal_none_when_modem_off(self, buffer_store, mock_hardware):
        for sensor in mock_hardware.values():
            if hasattr(sensor, "initialize"):
                await sensor.initialize()

        collector = TelemetryCollector(
            buffer=buffer_store,
            battery=mock_hardware["battery"],
            solar=mock_hardware["solar"],
            climate=mock_hardware["climate"],
            storage=mock_hardware["storage"],
            system=mock_hardware["system"],
            lte=mock_hardware["lte"],
        )

        reading = await collector.collect()
        assert reading["lte_signal_strength"] is None
        assert reading["lte_signal_quality"] is None

    async def test_update_lte_signal(self, buffer_store, mock_hardware):
        for sensor in mock_hardware.values():
            if hasattr(sensor, "initialize"):
                await sensor.initialize()

        # Power on LTE first
        await mock_hardware["lte"].power_on()

        collector = TelemetryCollector(
            buffer=buffer_store,
            battery=mock_hardware["battery"],
            solar=mock_hardware["solar"],
            climate=mock_hardware["climate"],
            storage=mock_hardware["storage"],
            system=mock_hardware["system"],
            lte=mock_hardware["lte"],
        )

        signal = await collector.update_lte_signal()
        assert signal["lte_signal_strength"] is not None
        assert signal["lte_signal_quality"] is not None

        # Next collect should have the signal
        reading = await collector.collect()
        assert reading["lte_signal_strength"] is not None
