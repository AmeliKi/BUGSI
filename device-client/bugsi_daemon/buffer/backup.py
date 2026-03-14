from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

DEFAULT_MAX_BACKUPS = 5


class BufferBackup:
    """Manages periodic SQLite database backups to USB stick."""

    def __init__(self, db_path: str, backup_dir: str, max_backups: int = DEFAULT_MAX_BACKUPS):
        self._db_path = db_path
        self._backup_dir = Path(backup_dir)
        self._max_backups = max_backups

    async def run_backup(self) -> str | None:
        """Create a consistent backup using VACUUM INTO. Returns backup path or None on error."""
        if not os.path.exists(self._db_path):
            logger.warning("Database file not found: %s", self._db_path)
            return None

        self._backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_path = self._backup_dir / f"buffer_backup_{timestamp}.db"

        try:
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute(f"VACUUM INTO ?", (str(backup_path),))
            logger.info("Backup created: %s", backup_path)
        except Exception:
            logger.exception("Backup failed")
            return None

        self._rotate_old_backups()
        return str(backup_path)

    def _rotate_old_backups(self) -> None:
        """Keep only the newest max_backups files, delete the rest."""
        if not self._backup_dir.exists():
            return

        backups = sorted(
            self._backup_dir.glob("buffer_backup_*.db"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        for old_backup in backups[self._max_backups:]:
            old_backup.unlink()
            logger.debug("Rotated old backup: %s", old_backup)
