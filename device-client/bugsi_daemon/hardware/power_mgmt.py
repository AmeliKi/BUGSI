"""Witty Pi 5 power management driver.

Uses the wp5 CLI tool to communicate with the RP2350 MCU for RTC
scheduling and power management.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from bugsi_daemon.hardware.base import PowerManagementInterface

logger = logging.getLogger(__name__)


class WittyPiPowerManager(PowerManagementInterface):
    """Witty Pi 5 - RTC and power scheduling via wp5 CLI."""

    async def initialize(self) -> None:
        # Verify wp5 CLI is available
        proc = await asyncio.create_subprocess_exec(
            "which", "wp5",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            raise NotImplementedError(
                "wp5 CLI not found — install Witty Pi 5 package"
            )
        logger.info("WittyPi5 initialized (wp5 at %s)", stdout.decode().strip())

    async def get_rtc_time(self) -> datetime:
        output = await self._run_wp5("get", "rtc_time")
        # Parse output like "2026-03-18 14:30:00"
        return datetime.strptime(output.strip(), "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )

    async def set_rtc_time(self, dt: datetime) -> None:
        time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        await self._run_wp5("set", "rtc_time", time_str)
        logger.info("RTC time set to %s", time_str)

    async def schedule_shutdown(self, at: datetime) -> None:
        time_str = at.strftime("%d %H:%M:%S")
        await self._run_wp5("set", "shutdown_time", time_str)
        logger.info("Shutdown scheduled at %s", at.isoformat())

    async def schedule_wakeup(self, at: datetime) -> None:
        time_str = at.strftime("%d %H:%M:%S")
        await self._run_wp5("set", "startup_time", time_str)
        logger.info("Wakeup scheduled at %s", at.isoformat())

    async def get_next_wakeup(self) -> datetime | None:
        try:
            output = await self._run_wp5("get", "startup_time")
            if output.strip() and output.strip() != "00 00:00:00":
                return datetime.strptime(
                    output.strip(), "%d %H:%M:%S"
                ).replace(tzinfo=timezone.utc)
        except Exception:
            logger.debug("No wakeup scheduled")
        return None

    async def get_wakeup_reason(self) -> str:
        try:
            output = await self._run_wp5("get", "wakeup_reason")
            reason = output.strip().lower()
            if "rtc" in reason or "alarm" in reason:
                return "rtc_wake"
        except Exception:
            logger.debug("Could not determine wakeup reason")
        return "cold_boot"

    async def get_temperature(self) -> float:
        output = await self._run_wp5("get", "temperature")
        return float(output.strip())

    async def get_input_voltage(self) -> float:
        output = await self._run_wp5("get", "input_voltage")
        return float(output.strip())

    async def shutdown(self) -> None:
        logger.info("WittyPi5 resources released")

    async def _run_wp5(self, *args: str) -> str:
        """Run wp5 CLI command and return stdout."""
        proc = await asyncio.create_subprocess_exec(
            "wp5", *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            error_msg = stderr.decode().strip()
            raise RuntimeError(f"wp5 {' '.join(args)} failed: {error_msg}")
        return stdout.decode()
