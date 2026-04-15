"""USB storage monitor.

Reads disk usage from the mounted USB stick via shutil.disk_usage.
"""
from __future__ import annotations

import logging
import os
import shutil

from bugsi_daemon.hardware.base import HardwareSensor

logger = logging.getLogger(__name__)


class UsbStorageMonitor(HardwareSensor):
    """Monitors USB stick disk usage at a mount point."""

    def __init__(self, mount_path: str = "/mnt/usb") -> None:
        self._mount_path = mount_path
        self._healthy = False

    async def initialize(self) -> None:
        self._healthy = os.path.exists(self._mount_path)
        if self._healthy:
            logger.info("UsbStorageMonitor initialized (mount=%s)", self._mount_path)
        else:
            logger.warning("USB mount path does not exist: %s", self._mount_path)

    async def read(self) -> dict:
        try:
            usage = shutil.disk_usage(self._mount_path)
            return {
                "storage_used_mb": int((usage.total - usage.free) / (1024 * 1024)),
                "storage_total_mb": int(usage.total / (1024 * 1024)),
            }
        except OSError:
            logger.warning("Failed to read disk usage for %s", self._mount_path)
            return {}

    async def shutdown(self) -> None:
        self._healthy = False

    def is_healthy(self) -> bool:
        return self._healthy and os.path.exists(self._mount_path)
