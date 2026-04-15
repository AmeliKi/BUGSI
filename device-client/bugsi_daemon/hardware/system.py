"""System monitor for Raspberry Pi.

Reads CPU temperature from sysfs and uptime from /proc/uptime.
"""
from __future__ import annotations

import logging
import os

from bugsi_daemon.hardware.base import HardwareSensor

logger = logging.getLogger(__name__)

THERMAL_ZONE_PATH = "/sys/class/thermal/thermal_zone0/temp"
UPTIME_PATH = "/proc/uptime"


class SystemMonitor(HardwareSensor):
    """Reads CPU temperature and system uptime from sysfs/procfs."""

    def __init__(self) -> None:
        self._healthy = False

    async def initialize(self) -> None:
        self._healthy = os.path.exists(THERMAL_ZONE_PATH)
        if self._healthy:
            logger.info("SystemMonitor initialized")
        else:
            logger.warning("Thermal zone not found at %s", THERMAL_ZONE_PATH)

    async def read(self) -> dict:
        result: dict = {}

        # CPU temperature
        try:
            with open(THERMAL_ZONE_PATH) as f:
                raw = f.read().strip()
            result["cpu_temp"] = round(int(raw) / 1000.0, 1)
        except (OSError, ValueError):
            logger.debug("Failed to read CPU temperature")

        # Uptime
        try:
            with open(UPTIME_PATH) as f:
                raw = f.read().strip()
            result["uptime_seconds"] = int(float(raw.split()[0]))
        except (OSError, ValueError, IndexError):
            logger.debug("Failed to read uptime")

        return result

    async def shutdown(self) -> None:
        self._healthy = False

    def is_healthy(self) -> bool:
        return self._healthy
