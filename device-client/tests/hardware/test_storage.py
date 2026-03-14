import pytest

from bugsi_daemon.hardware_mock.storage import MockStorage


@pytest.mark.asyncio
class TestMockStorage:
    async def test_initialize(self):
        storage = MockStorage()
        await storage.initialize()
        assert storage.is_healthy()

    async def test_read_returns_used_and_total(self):
        storage = MockStorage()
        await storage.initialize()
        data = await storage.read()

        assert "storage_used_mb" in data
        assert "storage_total_mb" in data
        assert data["storage_used_mb"] <= data["storage_total_mb"]

    async def test_custom_total(self):
        storage = MockStorage(total_mb=32000)
        await storage.initialize()
        data = await storage.read()
        assert data["storage_total_mb"] == 32000

    async def test_shutdown(self):
        storage = MockStorage()
        await storage.initialize()
        await storage.shutdown()
        assert not storage.is_healthy()
