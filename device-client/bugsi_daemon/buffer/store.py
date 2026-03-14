from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import aiosqlite

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS telemetry_buffer (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    synced INTEGER NOT NULL DEFAULT 0,
    synced_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS thumbnail_buffer (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    file_path TEXT NOT NULL,
    synced INTEGER NOT NULL DEFAULT 0,
    synced_at TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_telemetry_synced ON telemetry_buffer(synced);
CREATE INDEX IF NOT EXISTS idx_thumbnail_synced ON thumbnail_buffer(synced);
"""


class BufferStore:
    """SQLite-backed local buffer for telemetry and thumbnails."""

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA synchronous=NORMAL")
        await self._db.executescript(_SCHEMA)
        await self._db.commit()
        logger.info("Buffer store initialized at %s", self._db_path)

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    async def push_telemetry(self, reading: dict) -> int:
        now = datetime.now(timezone.utc).isoformat()
        timestamp = reading.get("timestamp", now)
        cursor = await self._db.execute(
            "INSERT INTO telemetry_buffer (timestamp, payload_json, created_at) VALUES (?, ?, ?)",
            (timestamp, json.dumps(reading), now),
        )
        await self._db.commit()
        return cursor.lastrowid

    async def push_thumbnail(self, file_path: str, timestamp: str) -> int:
        now = datetime.now(timezone.utc).isoformat()
        cursor = await self._db.execute(
            "INSERT INTO thumbnail_buffer (timestamp, file_path, created_at) "
            "VALUES (?, ?, ?)",
            (timestamp, file_path, now),
        )
        await self._db.commit()
        return cursor.lastrowid

    async def get_pending_telemetry(self, limit: int = 100) -> list[tuple[int, dict]]:
        cursor = await self._db.execute(
            "SELECT id, payload_json FROM telemetry_buffer WHERE synced = 0 ORDER BY id LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [(row[0], json.loads(row[1])) for row in rows]

    async def get_pending_thumbnails(self, limit: int = 100) -> list[tuple[int, str, str]]:
        """Returns list of (id, file_path, timestamp)."""
        cursor = await self._db.execute(
            "SELECT id, file_path, timestamp "
            "FROM thumbnail_buffer WHERE synced = 0 ORDER BY id LIMIT ?",
            (limit,),
        )
        return await cursor.fetchall()

    async def mark_synced(self, table: str, ids: list[int]) -> None:
        if not ids:
            return
        valid_tables = {"telemetry_buffer", "thumbnail_buffer"}
        if table not in valid_tables:
            raise ValueError(f"Invalid table: {table}")
        now = datetime.now(timezone.utc).isoformat()
        placeholders = ",".join("?" for _ in ids)
        await self._db.execute(
            f"UPDATE {table} SET synced = 1, synced_at = ? WHERE id IN ({placeholders})",
            [now, *ids],
        )
        await self._db.commit()

    async def cleanup_old(self, days: int = 30) -> int:
        """Remove synced records older than N days. Returns total deleted count."""
        cutoff = datetime.now(timezone.utc).isoformat()
        total = 0
        for table in ("telemetry_buffer", "thumbnail_buffer"):
            cursor = await self._db.execute(
                f"DELETE FROM {table} WHERE synced = 1 AND "
                f"julianday(?) - julianday(created_at) > ?",
                (cutoff, days),
            )
            total += cursor.rowcount
        await self._db.commit()
        logger.info("Cleaned up %d old synced records (older than %d days)", total, days)
        return total

    async def get_stats(self) -> dict:
        """Return buffer statistics."""
        stats = {}
        for table in ("telemetry_buffer", "thumbnail_buffer"):
            cursor = await self._db.execute(
                f"SELECT COUNT(*) FROM {table} WHERE synced = 0"
            )
            row = await cursor.fetchone()
            stats[f"{table}_pending"] = row[0]

            cursor = await self._db.execute(
                f"SELECT COUNT(*) FROM {table}"
            )
            row = await cursor.fetchone()
            stats[f"{table}_total"] = row[0]
        return stats
