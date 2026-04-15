from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from bugsi_daemon.buffer.backup import BufferBackup
from bugsi_daemon.buffer.store import BufferStore
from bugsi_daemon.config import ConfigManager
from bugsi_daemon.core.image_capture_pipeline import ImageCapturePipeline
from bugsi_daemon.core.mock_thumbnail_generator import MockThumbnailGenerator
from bugsi_daemon.core.power_manager import PowerManager
from bugsi_daemon.core.telemetry_collector import TelemetryCollector
from bugsi_daemon.core.upload_cycle import UploadCycle

logger = logging.getLogger(__name__)


class Scheduler:
    """Main daemon loop with power-aware periodic scheduling."""

    def __init__(
        self,
        config: ConfigManager,
        telemetry_collector: TelemetryCollector,
        upload_cycle: UploadCycle,
        power_manager: PowerManager,
        buffer: BufferStore,
        backup: BufferBackup,
        thumbnail_generator: MockThumbnailGenerator | None = None,
        image_pipeline: ImageCapturePipeline | None = None,
        web_server=None,
    ):
        self._config = config
        self._telemetry = telemetry_collector
        self._upload = upload_cycle
        self._power = power_manager
        self._buffer = buffer
        self._backup = backup
        self._thumbnail_gen = thumbnail_generator
        self._image_pipeline = image_pipeline
        self._web_server = web_server
        self._running = False
        self._tasks: list[asyncio.Task] = []
        self._last_battery_soc: float | None = None

    async def start(self) -> None:
        """Start the scheduler loop."""
        self._running = True
        logger.info("Scheduler started")

        self._tasks = [
            asyncio.create_task(self._telemetry_loop(), name="telemetry"),
            asyncio.create_task(self._upload_loop(), name="upload"),
            asyncio.create_task(self._backup_loop(), name="backup"),
        ]
        if self._image_pipeline:
            self._tasks.append(
                asyncio.create_task(self._image_capture_loop(), name="image_capture")
            )
        if self._web_server:
            self._tasks.append(
                asyncio.create_task(self._webserver_loop(), name="webserver")
            )

        try:
            await asyncio.gather(*self._tasks)
        except asyncio.CancelledError:
            logger.info("Scheduler tasks cancelled")
        finally:
            self._running = False
            self._tasks = []

    async def stop(self) -> None:
        """Signal the scheduler to stop and cancel all sleeping tasks."""
        self._running = False
        logger.info("Scheduler stop requested")
        for task in self._tasks:
            if not task.done():
                task.cancel()

    async def _webserver_loop(self) -> None:
        """Run the local webserver."""
        try:
            await self._web_server.start()
            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            await self._web_server.stop()

    async def _image_capture_loop(self) -> None:
        """Run the image capture pipeline (event camera detection → capture)."""
        try:
            await self._image_pipeline.run()
        except asyncio.CancelledError:
            pass
        finally:
            await self._image_pipeline.stop()

    async def shutdown(self) -> None:
        """Graceful shutdown: stop loops, prepare power off."""
        await self.stop()
        await self._power.prepare_shutdown()

    async def request_restart(self) -> None:
        """Request daemon restart (e.g. after config change).

        Unlike shutdown(), this does NOT call prepare_shutdown() so the
        system stays powered on.  systemd ``Restart=always`` will bring
        the daemon back up with the new configuration.
        """
        logger.info("Daemon restart requested")
        await self.stop()

    async def _telemetry_loop(self) -> None:
        """Collect telemetry every N minutes."""
        while self._running:
            interval = self._config.get("telemetry.collection_interval_minutes", 5)

            # Check power conditions
            now_hour = datetime.now(timezone.utc).hour
            if self._power.check_night_mode(now_hour):
                logger.info("Night mode detected, initiating shutdown")
                await self._power.prepare_shutdown()
                self._running = False
                return

            # Generate mock thumbnails (50% chance per cycle)
            if self._thumbnail_gen:
                try:
                    await self._thumbnail_gen.maybe_generate()
                except Exception:
                    logger.exception("Thumbnail generation failed")

            # Collect telemetry (includes pictures_taken count)
            extra = {}
            if self._image_pipeline:
                extra["pictures_taken"] = self._image_pipeline.pictures_taken
            elif self._thumbnail_gen:
                extra["pictures_taken"] = self._thumbnail_gen.pictures_taken

            try:
                reading = await self._telemetry.collect(extra=extra)
                self._last_battery_soc = reading.get("battery_soc")

                if self._last_battery_soc is not None and self._power.check_low_battery(self._last_battery_soc):
                    logger.warning("Low battery detected: %.1f%%", self._last_battery_soc)
                    from bugsi_daemon.core.power_manager import PowerMode
                    await self._power.set_mode(PowerMode.LOW_BATTERY)
            except Exception:
                logger.exception("Telemetry collection failed")

            await asyncio.sleep(interval * 60)

    async def _upload_loop(self) -> None:
        """Run upload cycle every M minutes."""
        while self._running:
            interval = self._config.get("upload.interval_minutes", 60)
            await asyncio.sleep(interval * 60)

            if not self._running:
                break

            try:
                await self._upload.run(last_battery_soc=self._last_battery_soc)
            except Exception:
                logger.exception("Upload cycle failed")

            # Cleanup old synced records
            cleanup_days = self._config.get("storage.cleanup_after_days", 30)
            try:
                await self._buffer.cleanup_old(cleanup_days)
            except Exception:
                logger.exception("Buffer cleanup failed")

    async def _backup_loop(self) -> None:
        """Backup database every K minutes."""
        while self._running:
            interval = self._config.get("storage.backup_interval_minutes", 60)
            await asyncio.sleep(interval * 60)

            if not self._running:
                break

            try:
                await self._backup.run_backup()
            except Exception:
                logger.exception("Backup failed")
