from __future__ import annotations

import logging

from bugsi_daemon.hardware.base import WlanInterface

logger = logging.getLogger(__name__)


class MockWlan(WlanInterface):
    """Mock WLAN control - logs actions and tracks state."""

    def __init__(self, has_internet: bool = False):
        self._enabled = True
        self._has_internet = has_internet

    async def enable(self) -> None:
        self._enabled = True
        logger.info("Mock WLAN enabled")

    async def disable(self) -> None:
        self._enabled = False
        logger.info("Mock WLAN disabled")

    def is_enabled(self) -> bool:
        return self._enabled

    async def has_internet(self) -> bool:
        return self._enabled and self._has_internet
