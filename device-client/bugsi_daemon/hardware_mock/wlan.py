from __future__ import annotations

import logging

from bugsi_daemon.hardware.base import WlanInterface

logger = logging.getLogger(__name__)


class MockWlan(WlanInterface):
    """Mock WLAN control - logs actions and tracks state."""

    def __init__(self, has_internet: bool = False, server_reachable: bool = False):
        self._enabled = True
        self._has_internet = has_internet
        self._server_reachable = server_reachable
        self._connected = False
        self._hotspot_active = False
        self._last_hotspot_ssid: str | None = None
        self._last_hotspot_password: str | None = None

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

    async def is_connected(self) -> bool:
        return self._enabled and self._connected

    async def start_hotspot(self, ssid: str, password: str) -> bool:
        self._hotspot_active = True
        self._connected = False
        self._last_hotspot_ssid = ssid
        self._last_hotspot_password = password
        logger.info("Mock hotspot '%s' started", ssid)
        return True

    async def stop_hotspot(self) -> None:
        self._hotspot_active = False
        logger.info("Mock hotspot stopped")

    async def is_hotspot_active(self) -> bool:
        return self._hotspot_active

    async def can_reach_host(self, host: str, port: int, timeout: float = 3.0) -> bool:
        return self._enabled and self._server_reachable
