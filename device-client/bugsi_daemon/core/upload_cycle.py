from __future__ import annotations

import logging

from bugsi_daemon.buffer.store import BufferStore
from bugsi_daemon.config import ConfigManager
from bugsi_daemon.core.power_manager import PowerManager, PowerMode
from bugsi_daemon.core.telemetry_collector import TelemetryCollector
from bugsi_daemon.net.client import BugsiClient

logger = logging.getLogger(__name__)


class UploadCycle:
    """Manages the periodic upload cycle: LTE on -> upload -> poll config -> LTE off."""

    def __init__(
        self,
        client: BugsiClient,
        buffer: BufferStore,
        config: ConfigManager,
        power_manager: PowerManager,
        telemetry_collector: TelemetryCollector,
    ):
        self._client = client
        self._buffer = buffer
        self._config = config
        self._power_manager = power_manager
        self._telemetry = telemetry_collector

    async def run(self, last_battery_soc: float | None = None) -> bool:
        """Run one upload cycle. Returns True if data was uploaded successfully."""
        # Check battery
        threshold = self._config.get("upload.battery_soc_threshold", 20)
        if last_battery_soc is not None and last_battery_soc < threshold:
            logger.warning(
                "Upload skipped: battery SoC %.1f%% below threshold %d%%",
                last_battery_soc, threshold,
            )
            return False

        try:
            # Power on LTE
            await self._power_manager.set_mode(PowerMode.UPLOAD)

            # Wait for network
            if not await self._power_manager._lte.wait_for_network(timeout=60):
                logger.error("Upload skipped: LTE network registration timeout")
                return False

            # Update LTE signal info
            await self._telemetry.update_lte_signal()

            # OTA check first (priority over data upload)
            if self._config.get("upload.ota_check_enabled", True):
                ota_applied = await self._check_and_apply_ota()
                if ota_applied:
                    return True

            # Upload telemetry
            await self._upload_telemetry()

            # Get latest config after telemetry upload
            await self._poll_config()

            # Upload only the latest thumbnail
            await self._upload_latest_thumbnail()

            # Get latest config after thumbnail upload
            await self._poll_config()

            # Push local config changes if any
            await self._push_config_if_needed()

            logger.info("Upload cycle completed successfully")
            return True

        except Exception:
            logger.exception("Upload cycle failed")
            return False
        finally:
            await self._power_manager.set_mode(PowerMode.ACTIVE)

    async def _check_and_apply_ota(self) -> bool:
        """Check for OTA update. Returns True if update was applied."""
        try:
            result = self._client.check_ota()
            if result.get("has_update"):
                deployment = result.get("deployment", result)
                logger.info("OTA update available, applying...")
                ota_result = self._client.process_ota_update(deployment)
                if ota_result["success"]:
                    logger.info("OTA applied successfully, restart may be required")
                    return True
                else:
                    logger.error("OTA failed: %s", ota_result.get("error"))
        except Exception:
            logger.exception("OTA check failed")
        return False

    async def _upload_telemetry(self) -> None:
        max_batch = self._config.get("upload.max_batch_size", 100)
        pending = await self._buffer.get_pending_telemetry(limit=max_batch)
        if not pending:
            logger.debug("No pending telemetry to upload")
            return

        ids = [item[0] for item in pending]
        readings = [item[1] for item in pending]

        try:
            self._client.send_telemetry(readings)
            await self._buffer.mark_synced("telemetry_buffer", ids)
            logger.info("Uploaded %d telemetry readings", len(readings))
        except Exception:
            logger.exception("Failed to upload telemetry")

    async def _upload_latest_thumbnail(self) -> None:
        """Upload only the single most recent unsynced thumbnail."""
        pending = await self._buffer.get_pending_thumbnails(limit=1)
        if not pending:
            return

        row_id, file_path, timestamp = pending[0]
        try:
            with open(file_path, "rb") as f:
                image_data = f.read()
            self._client.upload_thumbnail(image_data, timestamp)
            await self._buffer.mark_synced("thumbnail_buffer", [row_id])
            logger.info("Uploaded latest thumbnail: %s", file_path)
        except FileNotFoundError:
            logger.warning("Thumbnail file not found: %s, marking as synced", file_path)
            await self._buffer.mark_synced("thumbnail_buffer", [row_id])
        except Exception:
            logger.exception("Failed to upload thumbnail %s", file_path)

    async def _push_config_if_needed(self) -> None:
        if not self._config.has_unpushed_changes:
            return
        try:
            self._client.push_config(self._config.get_all(), self._config.version)
            self._config.clear_unpushed()
            logger.info("Pushed local config v%d to SaaS", self._config.version)
        except Exception:
            logger.exception("Failed to push local config to SaaS")

    async def _poll_config(self) -> None:
        try:
            result = self._client.poll_config()
            if result.get("has_update"):
                version = result["version"]
                config_data = result["config"]
                changed = self._config.apply_remote(config_data, version)
                if changed:
                    self._client.ack_config(version)
                    logger.info("Config updated to v%d and acknowledged", version)
        except Exception:
            logger.exception("Failed to poll config")
