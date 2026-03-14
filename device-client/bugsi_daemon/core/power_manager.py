from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from enum import Enum

from bugsi_daemon.buffer.backup import BufferBackup
from bugsi_daemon.config import ConfigManager
from bugsi_daemon.hardware.base import LteModemInterface, PowerManagementInterface

logger = logging.getLogger(__name__)


class PowerMode(Enum):
    ACTIVE = "active"
    UPLOAD = "upload"
    NIGHT = "night"
    LOW_BATTERY = "low_battery"


class PowerManager:
    """Orchestrates hardware power states based on config and conditions."""

    def __init__(
        self,
        config: ConfigManager,
        lte: LteModemInterface,
        power_mgmt: PowerManagementInterface,
        backup: BufferBackup,
    ):
        self._config = config
        self._lte = lte
        self._power_mgmt = power_mgmt
        self._backup = backup
        self._mode = PowerMode.ACTIVE

    @property
    def mode(self) -> PowerMode:
        return self._mode

    async def set_mode(self, mode: PowerMode) -> None:
        if mode == self._mode:
            return

        old_mode = self._mode
        logger.info("Power mode: %s -> %s", old_mode.value, mode.value)

        if mode == PowerMode.UPLOAD:
            await self._lte.power_on()
        elif mode == PowerMode.ACTIVE and old_mode == PowerMode.UPLOAD:
            await self._lte.power_off()
        elif mode == PowerMode.LOW_BATTERY:
            if self._lte.is_powered():
                await self._lte.power_off()
        elif mode == PowerMode.NIGHT:
            if self._lte.is_powered():
                await self._lte.power_off()

        self._mode = mode

    def check_night_mode(self, current_hour: int) -> bool:
        """Return True if the system should enter night mode."""
        if not self._config.get("power.night_mode_enabled", True):
            return False
        start = self._config.get("power.night_start_hour", 22)
        end = self._config.get("power.night_end_hour", 6)
        if start > end:
            return current_hour >= start or current_hour < end
        return start <= current_hour < end

    def check_low_battery(self, soc: float) -> bool:
        """Return True if battery is below threshold."""
        threshold = self._config.get("upload.battery_soc_threshold", 20)
        return soc < threshold

    async def schedule_wakeup(self, hour: int) -> None:
        """Schedule next wakeup via Witty Pi RTC."""
        now = datetime.now(timezone.utc)
        wakeup = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if wakeup <= now:
            wakeup += timedelta(days=1)
        await self._power_mgmt.schedule_wakeup(wakeup)
        logger.info("Wakeup scheduled for %s", wakeup.isoformat())

    async def prepare_shutdown(self) -> None:
        """Graceful shutdown: backup DB, schedule wakeup, power off hardware."""
        logger.info("Preparing for shutdown...")

        # Backup database
        await self._backup.run_backup()

        # Power off LTE if on
        if self._lte.is_powered():
            await self._lte.power_off()

        # Schedule wakeup for morning
        end_hour = self._config.get("power.night_end_hour", 6)
        await self.schedule_wakeup(end_hour)

        # Schedule shutdown in 1 minute
        shutdown_time = datetime.now(timezone.utc) + timedelta(minutes=1)
        await self._power_mgmt.schedule_shutdown(shutdown_time)

        self._mode = PowerMode.NIGHT
        logger.info("Shutdown prepared, system will power off shortly")
