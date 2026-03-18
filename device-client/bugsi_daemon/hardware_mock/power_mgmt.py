from __future__ import annotations

import logging
import random
from datetime import datetime, timezone

from bugsi_daemon.hardware.base import PowerManagementInterface

logger = logging.getLogger(__name__)


class MockPowerManagement(PowerManagementInterface):
    """Mock Witty Pi 5 - logs actions instead of real hardware commands."""

    def __init__(self):
        self._next_wakeup: datetime | None = None
        self._next_shutdown: datetime | None = None

    async def initialize(self) -> None:
        logger.info("Mock Witty Pi initialized")

    async def get_rtc_time(self) -> datetime:
        return datetime.now(timezone.utc)

    async def set_rtc_time(self, dt: datetime) -> None:
        logger.info("Mock RTC time set to %s", dt.isoformat())

    async def schedule_shutdown(self, at: datetime) -> None:
        self._next_shutdown = at
        logger.info("Mock shutdown scheduled at %s", at.isoformat())

    async def schedule_wakeup(self, at: datetime) -> None:
        self._next_wakeup = at
        logger.info("Mock wakeup scheduled at %s", at.isoformat())

    async def get_next_wakeup(self) -> datetime | None:
        return self._next_wakeup

    async def get_wakeup_reason(self) -> str:
        logger.info("Mock wakeup reason: cold_boot")
        return "cold_boot"

    async def get_temperature(self) -> float:
        temp = round(random.uniform(20.0, 30.0), 1)
        logger.debug("Mock Witty Pi temperature: %.1f°C", temp)
        return temp

    async def get_input_voltage(self) -> float:
        voltage = round(random.uniform(11.5, 12.5), 2)
        logger.debug("Mock Witty Pi input voltage: %.2fV", voltage)
        return voltage

    async def shutdown(self) -> None:
        logger.info("Mock Witty Pi shutdown")
