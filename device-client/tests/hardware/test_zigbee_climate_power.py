import pytest

from bugsi_daemon.hardware.base import HardwareSensor, PowerControllable
from bugsi_daemon.hardware_mock.climate import MockClimate


@pytest.mark.asyncio
class TestMockClimatePower:
    async def test_implements_interfaces(self):
        climate = MockClimate()
        assert isinstance(climate, HardwareSensor)
        assert isinstance(climate, PowerControllable)

    async def test_starts_powered_off(self):
        climate = MockClimate()
        assert not climate.is_powered()
        assert not climate.is_healthy()

    async def test_power_on_off(self):
        climate = MockClimate()
        await climate.power_on()
        assert climate.is_powered()
        assert climate.is_healthy()
        await climate.power_off()
        assert not climate.is_powered()
        assert not climate.is_healthy()

    async def test_read_when_powered(self):
        climate = MockClimate()
        await climate.power_on()
        reading = await climate.read()
        assert "temperature" in reading
        assert "humidity" in reading
        assert 5.0 <= reading["temperature"] <= 35.0
        assert 30.0 <= reading["humidity"] <= 90.0

    async def test_read_when_powered_off_returns_last_known(self):
        climate = MockClimate()
        await climate.power_on()
        reading1 = await climate.read()
        await climate.power_off()
        reading2 = await climate.read()
        # Should return the last known values
        assert reading2 == reading1

    async def test_read_when_never_powered_returns_empty(self):
        climate = MockClimate()
        reading = await climate.read()
        assert reading == {}

    async def test_initialize_powers_on(self):
        climate = MockClimate()
        await climate.initialize()
        assert climate.is_powered()
        assert climate.is_healthy()
