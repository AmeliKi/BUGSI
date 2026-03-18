from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from enum import Enum

from bugsi_daemon.buffer.backup import BufferBackup
from bugsi_daemon.config import ConfigManager
from bugsi_daemon.hardware.base import (
    LteModemInterface,
    PowerManagementInterface,
    WlanInterface,
)

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
        wlan: WlanInterface | None = None,
    ):
        self._config = config
        self._lte = lte
        self._power_mgmt = power_mgmt
        self._backup = backup
        self._wlan = wlan
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

    def get_active_hours(self) -> tuple[int, int]:
        """Return (awake_start_hour, awake_end_hour) based on config mode."""
        mode_type = self._config.get("power.night_mode_type", "fixed")

        if mode_type == "sunrise_sunset":
            lat = self._config.get("power.location_lat")
            lon = self._config.get("power.location_lon")
            if lat is not None and lon is not None:
                try:
                    from astral import LocationInfo
                    from astral.sun import sun

                    loc = LocationInfo(latitude=lat, longitude=lon)
                    s = sun(loc.observer, date=datetime.now().date())
                    sunrise_offset = self._config.get(
                        "power.sunrise_offset_minutes", 0
                    )
                    sunset_offset = self._config.get(
                        "power.sunset_offset_minutes", 0
                    )
                    start = (
                        s["sunrise"] + timedelta(minutes=sunrise_offset)
                    ).hour
                    end = (
                        s["sunset"] + timedelta(minutes=sunset_offset)
                    ).hour
                    return (start, end)
                except Exception:
                    logger.exception(
                        "Sunrise/sunset calculation failed, falling back to fixed"
                    )

        # Fixed mode (default: awake 7-21)
        return (
            self._config.get("power.awake_start_hour", 7),
            self._config.get("power.awake_end_hour", 21),
        )

    def check_night_mode(self, current_hour: int) -> bool:
        """Return True if the system should enter night mode (outside active hours)."""
        if not self._config.get("power.night_mode_enabled", True):
            return False
        start, end = self.get_active_hours()
        # Active during [start, end), sleep otherwise
        if start < end:
            return current_hour < start or current_hour >= end
        # Wraps midnight (e.g. start=21, end=7 means active 21-7)
        return current_hour >= end and current_hour < start

    def check_low_battery(self, soc: float) -> bool:
        """Return True if battery is below threshold."""
        threshold = self._config.get("upload.battery_soc_threshold", 20)
        return soc < threshold

    async def apply_energy_saving(self, boot_type: str) -> None:
        """Apply energy saving mode based on config and boot type."""
        if not self._config.get("power.energy_saving", False):
            return

        if boot_type == "rtc_wake":
            # RTC wake: disable WLAN immediately to save power
            if self._wlan:
                await self._wlan.disable()
                logger.info("Energy saving: WLAN disabled (RTC wake)")
        else:
            # Cold boot: WLAN stays on for configured minutes
            # (WlanManager handles the timeout via its inactivity timer)
            logger.info("Energy saving: cold boot, WLAN timeout applies")

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

        # Schedule wakeup for morning based on active hours
        start_hour, _ = self.get_active_hours()
        await self.schedule_wakeup(start_hour)

        # Schedule shutdown in 1 minute
        shutdown_time = datetime.now(timezone.utc) + timedelta(minutes=1)
        await self._power_mgmt.schedule_shutdown(shutdown_time)

        self._mode = PowerMode.NIGHT
        logger.info("Shutdown prepared, system will power off shortly")
