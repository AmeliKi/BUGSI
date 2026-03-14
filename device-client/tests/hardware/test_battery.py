import pytest

from bugsi_daemon.hardware_mock.battery import MockBattery


@pytest.mark.asyncio
class TestMockBattery:
    async def test_initialize(self):
        battery = MockBattery()
        await battery.initialize()
        assert battery.is_healthy()

    async def test_read_returns_all_fields(self):
        battery = MockBattery()
        await battery.initialize()
        data = await battery.read()

        assert "battery_voltage" in data
        assert "battery_soc" in data
        assert "battery_current" in data
        assert "battery_power" in data
        assert "battery_consumed_ah" in data
        assert "battery_ttg_min" in data

    async def test_read_values_in_range(self):
        battery = MockBattery()
        await battery.initialize()
        data = await battery.read()

        assert 24.0 <= data["battery_voltage"] <= 28.0
        assert 0.0 <= data["battery_soc"] <= 100.0
        assert -3.0 <= data["battery_current"] <= 1.0
        assert data["battery_power"] >= 0
        assert data["battery_consumed_ah"] >= 0
        assert data["battery_ttg_min"] >= 0

    async def test_shutdown(self):
        battery = MockBattery()
        await battery.initialize()
        assert battery.is_healthy()
        await battery.shutdown()
        assert not battery.is_healthy()

    async def test_soc_changes_over_multiple_reads(self):
        battery = MockBattery()
        await battery.initialize()
        readings = [await battery.read() for _ in range(10)]
        soc_values = [r["battery_soc"] for r in readings]
        # Over 10 reads, there should be at least 2 distinct SoC values
        assert len(set(soc_values)) >= 2
