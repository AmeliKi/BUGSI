import pytest

from bugsi_daemon.buffer.backup import BufferBackup
from bugsi_daemon.buffer.store import BufferStore


@pytest.mark.asyncio
class TestBufferBackup:
    async def test_run_backup_creates_file(self, tmp_path):
        db_path = str(tmp_path / "buffer.db")
        store = BufferStore(db_path)
        await store.initialize()
        await store.push_telemetry({"timestamp": "2026-03-07T12:00:00Z"})

        backup = BufferBackup(db_path, str(tmp_path / "backups"))
        result = await backup.run_backup()

        assert result is not None
        assert "buffer_backup_" in result
        await store.close()

    async def test_rotation_keeps_max_backups(self, tmp_path):
        db_path = str(tmp_path / "buffer.db")
        store = BufferStore(db_path)
        await store.initialize()

        backup_dir = tmp_path / "backups"
        backup = BufferBackup(db_path, str(backup_dir), max_backups=2)

        # Create 3 backups
        for _ in range(3):
            await backup.run_backup()

        backup_files = list(backup_dir.glob("buffer_backup_*.db"))
        assert len(backup_files) <= 2
        await store.close()

    async def test_backup_nonexistent_db(self, tmp_path):
        backup = BufferBackup("/nonexistent/path.db", str(tmp_path / "backups"))
        result = await backup.run_backup()
        assert result is None
