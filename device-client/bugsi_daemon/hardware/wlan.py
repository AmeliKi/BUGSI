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

    async def is_connected(self) -> bool:
        """Check if connected to an infrastructure WiFi network (not hotspot)."""
        if not self._enabled:
            return False
        try:
            proc = await asyncio.create_subprocess_exec(
                "nmcli", "-t", "-f", "NAME,TYPE", "connection", "show", "--active",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await proc.communicate()
            for line in stdout.decode().strip().splitlines():
                parts = line.split(":")
                if len(parts) >= 2 and "wireless" in parts[1] and parts[0] != "bugsi-hotspot":
                    return True
            return False
        except Exception:
            return False

    async def start_hotspot(self, ssid: str, password: str) -> bool:
        """Start a WiFi AP hotspot using nmcli."""
        # Check if the bugsi-hotspot profile already exists
        check = await asyncio.create_subprocess_exec(
            "nmcli", "-t", "-f", "NAME", "connection", "show",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await check.communicate()
        profile_exists = "bugsi-hotspot" in stdout.decode()

        if not profile_exists:
            # Create the connection profile
            proc = await asyncio.create_subprocess_exec(
                "nmcli", "connection", "add",
                "type", "wifi",
                "ifname", self._interface,
                "con-name", "bugsi-hotspot",
                "autoconnect", "no",
                "wifi.mode", "ap",
                "wifi.ssid", ssid,
                "wifi-sec.key-mgmt", "wpa-psk",
                "wifi-sec.psk", password,
                "ipv4.method", "shared",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                logger.error("Failed to create hotspot profile: %s", stderr.decode().strip())
                return False
        else:
            # Update existing profile with current SSID and password
            for prop, val in [("wifi.ssid", ssid), ("wifi-sec.psk", password)]:
                await asyncio.create_subprocess_exec(
                    "nmcli", "connection", "modify", "bugsi-hotspot", prop, val,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )

        # Activate the hotspot
        proc = await asyncio.create_subprocess_exec(
            "nmcli", "connection", "up", "bugsi-hotspot",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.error("Failed to start hotspot: %s", stderr.decode().strip())
            return False

        logger.info("Hotspot '%s' started on %s", ssid, self._interface)
        return True

    async def stop_hotspot(self) -> None:
        """Stop the WiFi AP hotspot."""
        proc = await asyncio.create_subprocess_exec(
            "nmcli", "connection", "down", "bugsi-hotspot",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.warning("Failed to stop hotspot: %s", stderr.decode().strip())
        else:
            logger.info("Hotspot stopped")

    async def is_hotspot_active(self) -> bool:
        """Check if the bugsi-hotspot connection is active."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "nmcli", "-t", "-f", "NAME", "connection", "show", "--active",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await proc.communicate()
            return "bugsi-hotspot" in stdout.decode()
        except Exception:
            return False
