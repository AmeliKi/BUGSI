"""Routing helpers for LTE uploads when WiFi AP is active."""
from __future__ import annotations

import asyncio
import logging
import socket
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def resolve_server_host(base_url: str) -> tuple[str, int]:
    """Parse the base URL and return (host, port)."""
    parsed = urlparse(base_url)
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return host, port


def resolve_ip(host: str) -> str | None:
    """Resolve hostname to an IPv4 address. Returns None on failure."""
    try:
        return socket.gethostbyname(host)
    except socket.gaierror:
        return None


class LteRoute:
    """Async context manager that adds/removes a host-specific route via the LTE interface.

    When the WiFi AP is active with ipv4.method=shared, its routing/NAT rules
    can capture outbound traffic. This forces traffic to a specific server IP
    through the LTE network interface instead.
    """

    def __init__(self, server_ip: str, lte_interface: str):
        self._server_ip = server_ip
        self._lte_interface = lte_interface
        self._route_added = False

    async def __aenter__(self) -> LteRoute:
        proc = await asyncio.create_subprocess_exec(
            "ip", "route", "add", f"{self._server_ip}/32", "dev", self._lte_interface,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode == 0:
            self._route_added = True
            logger.info(
                "Added route %s/32 dev %s", self._server_ip, self._lte_interface
            )
        else:
            err_msg = stderr.decode().strip()
            if "File exists" in err_msg:
                self._route_added = True
                logger.debug(
                    "Route %s/32 dev %s already exists",
                    self._server_ip, self._lte_interface,
                )
            else:
                logger.error("Failed to add LTE route: %s", err_msg)
        return self

    async def __aexit__(self, *exc) -> None:
        if not self._route_added:
            return
        proc = await asyncio.create_subprocess_exec(
            "ip", "route", "del", f"{self._server_ip}/32", "dev", self._lte_interface,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.communicate()
        if proc.returncode == 0:
            logger.info(
                "Removed route %s/32 dev %s", self._server_ip, self._lte_interface
            )
