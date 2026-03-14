import pytest

from bugsi_daemon.hardware_mock.system import MockSystem


@pytest.mark.asyncio
class TestMockSystem:
    async def test_initialize(self):
        system = MockSystem()
        await system.initialize()
        assert system.is_healthy()

    async def test_read_returns_cpu_temp_and_uptime(self):
        system = MockSystem()
        await system.initialize()
        data = await system.read()

        assert "cpu_temp" in data
        assert "uptime_seconds" in data

    async def test_cpu_temp_in_range(self):
        system = MockSystem()
        await system.initialize()
        data = await system.read()
        assert 35.0 <= data["cpu_temp"] <= 65.0

    async def test_uptime_non_negative(self):
        system = MockSystem()
        await system.initialize()
        data = await system.read()
        assert data["uptime_seconds"] >= 0

    async def test_shutdown(self):
        system = MockSystem()
        await system.initialize()
        await system.shutdown()
        assert not system.is_healthy()
