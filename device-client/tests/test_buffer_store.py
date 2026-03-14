import pytest

from bugsi_daemon.buffer.store import BufferStore


@pytest.mark.asyncio
class TestBufferStore:
    async def test_push_and_get_telemetry(self, buffer_store):
        reading = {"timestamp": "2026-03-07T12:00:00Z", "battery_soc": 75.0}
        row_id = await buffer_store.push_telemetry(reading)
        assert row_id > 0

        pending = await buffer_store.get_pending_telemetry()
        assert len(pending) == 1
        assert pending[0][0] == row_id
        assert pending[0][1]["battery_soc"] == 75.0

    async def test_push_thumbnail(self, buffer_store):
        row_id = await buffer_store.push_thumbnail("/path/to/image.jpg", "2026-03-07T12:00:00Z")
        assert row_id > 0

        pending = await buffer_store.get_pending_thumbnails()
        assert len(pending) == 1
        assert pending[0][1] == "/path/to/image.jpg"

    async def test_mark_synced(self, buffer_store):
        id1 = await buffer_store.push_telemetry({"timestamp": "2026-03-07T12:00:00Z", "battery_soc": 75.0})
        id2 = await buffer_store.push_telemetry({"timestamp": "2026-03-07T12:01:00Z", "battery_soc": 74.0})

        await buffer_store.mark_synced("telemetry_buffer", [id1])

        pending = await buffer_store.get_pending_telemetry()
        assert len(pending) == 1
        assert pending[0][0] == id2

    async def test_get_pending_respects_limit(self, buffer_store):
        for i in range(5):
            await buffer_store.push_telemetry({"timestamp": f"2026-03-07T12:0{i}:00Z", "battery_soc": 70 + i})

        pending = await buffer_store.get_pending_telemetry(limit=3)
        assert len(pending) == 3

    async def test_cleanup_old_removes_only_synced(self, buffer_store):
        id1 = await buffer_store.push_telemetry({"timestamp": "2026-03-07T12:00:00Z"})
        id2 = await buffer_store.push_telemetry({"timestamp": "2026-03-07T12:01:00Z"})

        await buffer_store.mark_synced("telemetry_buffer", [id1])

        # Cleanup with -1 days removes all synced records regardless of age
        deleted = await buffer_store.cleanup_old(days=-1)
        assert deleted >= 1

        # Unsynced record should remain
        pending = await buffer_store.get_pending_telemetry()
        assert len(pending) == 1
        assert pending[0][0] == id2

    async def test_mark_synced_invalid_table(self, buffer_store):
        with pytest.raises(ValueError, match="Invalid table"):
            await buffer_store.mark_synced("invalid_table", [1])

    async def test_get_stats(self, buffer_store):
        await buffer_store.push_telemetry({"timestamp": "2026-03-07T12:00:00Z"})

        stats = await buffer_store.get_stats()
        assert stats["telemetry_buffer_pending"] == 1
        assert stats["thumbnail_buffer_pending"] == 0
