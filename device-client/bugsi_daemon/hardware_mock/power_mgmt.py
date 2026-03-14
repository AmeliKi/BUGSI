from __future__ import annotations

import logging
from datetime import datetime, timezone

from bugsi_daemon.hardware.base import PowerManagementInterface

logger = logging.getLogger(__name__)


class MockPowerManagement(PowerManagementInterface):
    """Mock Witty Pi 4 Mini - logs actions instead of real I2C commands."""

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

    async def shutdown(self) -> None:
        logger.info("Mock Witty Pi shutdown")
