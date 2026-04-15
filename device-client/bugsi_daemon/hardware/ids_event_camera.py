"""IDS uEye EVS event camera driver.

Subclasses PropheseeEventCamera since the IDS uEye EVS uses the same
OpenEB/Metavision SDK. The key difference is the device path resolution:
the IDS camera connects via USB and uses an empty string for auto-detection
instead of scanning sysfs for a V4L2 device.
"""
from __future__ import annotations

import logging

from bugsi_daemon.hardware.base import register_event_camera
from bugsi_daemon.hardware.event_camera import PropheseeEventCamera

logger = logging.getLogger(__name__)


@register_event_camera("ids_evs")
class IDSEventCamera(PropheseeEventCamera):
    """IDS uEye EVS event camera via OpenEB/Metavision SDK (USB)."""

    @staticmethod
    def _resolve_device_path(configured_path: str) -> str:
        """Resolve device path for the IDS uEye EVS.

        The IDS event camera connects via USB and is auto-detected by OpenEB
        when an empty string is passed as the input path.
        """
        if configured_path == "auto":
            logger.info("IDS EVS: using empty path for USB auto-detection")
            return ""
        return configured_path

    async def initialize(self) -> None:
        try:
            from metavision_core.event_io import EventsIterator  # noqa: F401
        except ImportError:
            raise NotImplementedError(
                "metavision_core not available — install OpenEB SDK"
            )
        # Skip os.path.exists check — empty string is valid for USB auto-detect
        self._powered = True
        logger.info("IDSEventCamera initialized (device=%s)", self._device_path or "(USB auto)")
