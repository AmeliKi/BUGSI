from __future__ import annotations

import asyncio
import logging

from bugsi_daemon.hardware.base import WlanInterface

logger = logging.getLogger(__name__)


class SystemWlan(WlanInterface):
    """Real WLAN control via nmcli on Raspberry Pi."""

    def __init__(self, interface: str = "wlan0"):
        self._interface = interface
        self._enabled = True

    async def enable(self) -> None:
        proc = await asyncio.create_subprocess_exec(
            "nmcli", "radio", "wifi", "on",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.error("Failed to enable WLAN: %s", stderr.decode().strip())
        else:
            self._enabled = True
            logger.info("WLAN enabled")

    async def disable(self) -> None:
        proc = await asyncio.create_subprocess_exec(
            "nmcli", "radio", "wifi", "off",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.error("Failed to disable WLAN: %s", stderr.decode().strip())
        else:
            self._enabled = False
            logger.info("WLAN disabled")

    def is_enabled(self) -> bool:
        return self._enabled

    async def has_internet(self) -> bool:
        """Check internet connectivity by pinging a public DNS server."""
        if not self._enabled:
            return False
        try:
            proc = await asyncio.create_subprocess_exec(
                "ping", "-c", "1", "-W", "3", "1.1.1.1",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.communicate()
            return proc.returncode == 0
        except Exception:
            return False
