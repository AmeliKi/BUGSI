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
        self._ap_fallback_task: asyncio.Task | None = None
        self._webserver_active = False
        self._battery_mode = False
        self._ap_mode = False

    @property
    def battery_mode(self) -> bool:
        return self._battery_mode

    @property
    def ap_mode(self) -> bool:
        return self._ap_mode

    async def start(self, boot_type: str) -> bool:
        """Decide whether to enable WLAN based on config and boot type.

        Returns True if the webserver should be started.
        """
        self._battery_mode = self._config.get("power.battery", False)

        if not self._battery_mode:
            logger.info("Battery mode disabled, WLAN always on")
            await self._try_connect_or_ap()
            return True

        if boot_type == "rtc_wake":
            logger.info("RTC wake detected with battery mode, keeping WLAN off")
            return False

        # Cold boot with battery mode: enable WLAN with timeout
        logger.info("Cold boot with battery mode, enabling WLAN with inactivity timer")
        await self._wlan.enable()
        self._webserver_active = True
        self._start_timer()
        await self._try_connect_or_ap()
        return True

    async def _try_connect_or_ap(self) -> None:
        """Try to connect to a known network; start AP if unavailable."""
        if not self._config.get("wifi.ap_fallback_enabled", True):
            return

        # Wait for NetworkManager to auto-connect to a known network
        wait = self._config.get("wifi.ap_connect_wait_seconds", 10)
        await asyncio.sleep(wait)

        if await self._wlan.is_connected():
            logger.info("Connected to known WiFi network")
            return

        # No known network available, start AP
        ssid = self._config.get("wifi.ap_ssid", "BUGSI-Setup")
        password = self._config.get("wifi.ap_password", "bugsi1234")
        success = await self._wlan.start_hotspot(ssid, password)
        if success:
            self._ap_mode = True
            logger.info("No known network found, started AP hotspot '%s'", ssid)
            self._start_ap_recheck()
        else:
            logger.error("Failed to start AP hotspot")

    def _start_ap_recheck(self) -> None:
        """Start the periodic background task to check for known networks."""
        if self._ap_fallback_task and not self._ap_fallback_task.done():
            return
        self._ap_fallback_task = asyncio.create_task(self._ap_recheck_loop())

    async def _ap_recheck_loop(self) -> None:
        """Periodically check if a known network became available."""
        interval = self._config.get("wifi.ap_recheck_interval_minutes", 5)
        try:
            while self._ap_mode:
                await asyncio.sleep(interval * 60)
                if not self._ap_mode:
                    break
                logger.info("Rechecking for known WiFi networks...")
                # Stop hotspot to allow scanning
                await self._wlan.stop_hotspot()
                # Give NM time to scan and auto-connect
                wait = self._config.get("wifi.ap_connect_wait_seconds", 10)
                await asyncio.sleep(wait)
                if await self._wlan.is_connected():
                    logger.info("Known network found, switched to client mode")
                    self._ap_mode = False
                    return
                # No known network, restart AP
                ssid = self._config.get("wifi.ap_ssid", "BUGSI-Setup")
                password = self._config.get("wifi.ap_password", "bugsi1234")
                await self._wlan.start_hotspot(ssid, password)
                logger.info("No known network found, re-started AP hotspot")
        except asyncio.CancelledError:
            pass

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
            if self._ap_mode:
                await self._wlan.stop_hotspot()
                self._ap_mode = False
            if self._ap_fallback_task and not self._ap_fallback_task.done():
                self._ap_fallback_task.cancel()
            await self._wlan.disable()
            self._webserver_active = False
        except asyncio.CancelledError:
            pass  # Timer was reset

    async def stop(self) -> None:
        """Cancel all background tasks and clean up hotspot."""
        if self._timer_task and not self._timer_task.done():
            self._timer_task.cancel()
            try:
                await self._timer_task
            except asyncio.CancelledError:
                pass

        if self._ap_fallback_task and not self._ap_fallback_task.done():
            self._ap_fallback_task.cancel()
            try:
                await self._ap_fallback_task
            except asyncio.CancelledError:
                pass

        if self._ap_mode:
            await self._wlan.stop_hotspot()
            self._ap_mode = False
