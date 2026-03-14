from __future__ import annotations

import asyncio
import logging

from bugsi_daemon.config import ConfigManager
from bugsi_daemon.hardware.base import WlanInterface

logger = logging.getLogger(__name__)


class WlanManager:
    """Manages WLAN power state based on battery mode and user activity."""

    def __init__(
        self,
        config: ConfigManager,
        wlan: WlanInterface,
    ):
        self._config = config
        self._wlan = wlan
        self._timer_task: asyncio.Task | None = None
        self._webserver_active = False
        self._battery_mode = False

    @property
    def battery_mode(self) -> bool:
        return self._battery_mode

    async def start(self, boot_type: str) -> bool:
        """Decide whether to enable WLAN based on config and boot type.

        Returns True if the webserver should be started.
        """
        self._battery_mode = self._config.get("power.battery", False)

        if not self._battery_mode:
            logger.info("Battery mode disabled, WLAN always on")
            return True

        if boot_type == "rtc_wake":
            logger.info("RTC wake detected with battery mode, keeping WLAN off")
            return False

        # Cold boot with battery mode: enable WLAN with timeout
        logger.info("Cold boot with battery mode, enabling WLAN with inactivity timer")
        await self._wlan.enable()
        self._webserver_active = True
        self._start_timer()
        return True

    def reset_timer(self) -> None:
        """Reset the inactivity timer. Called on each web request."""
        if not self._battery_mode:
            return
        if self._timer_task and not self._timer_task.done():
            self._timer_task.cancel()
        self._start_timer()

    def _start_timer(self) -> None:
        timeout_minutes = self._config.get("power.wlan_timeout_minutes", 10)
        self._timer_task = asyncio.create_task(
            self._inactivity_timeout(timeout_minutes)
        )

    async def _inactivity_timeout(self, minutes: float) -> None:
        try:
            await asyncio.sleep(minutes * 60)
            logger.info("WLAN inactivity timeout reached (%s min), disabling WLAN", minutes)
            await self._wlan.disable()
            self._webserver_active = False
        except asyncio.CancelledError:
            pass  # Timer was reset

    async def stop(self) -> None:
        """Cancel the timer task."""
        if self._timer_task and not self._timer_task.done():
            self._timer_task.cancel()
            try:
                await self._timer_task
            except asyncio.CancelledError:
                pass
