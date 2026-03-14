import pytest

from bugsi_daemon.hardware_mock.climate import MockClimate


@pytest.mark.asyncio
class TestMockClimate:
    async def test_initialize(self):
        sensor = MockClimate()
        await sensor.initialize()
        assert sensor.is_healthy()

    async def test_read_returns_temp_and_humidity(self):
        sensor = MockClimate()
        await sensor.initialize()
        data = await sensor.read()

        assert "temperature" in data
        assert "humidity" in data

    async def test_values_in_range(self):
        sensor = MockClimate()
        await sensor.initialize()
        data = await sensor.read()

        assert 5.0 <= data["temperature"] <= 35.0
        assert 30.0 <= data["humidity"] <= 90.0

    async def test_shutdown(self):
        sensor = MockClimate()
        await sensor.initialize()
        await sensor.shutdown()
        assert not sensor.is_healthy()
