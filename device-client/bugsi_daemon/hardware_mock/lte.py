from __future__ import annotations

import asyncio
import random

from bugsi_daemon.hardware.base import LteModemInterface


class MockLteModem(LteModemInterface):
    """Mock Sixfab EG25-G LTE modem."""

    def __init__(self):
        self._powered = False

    async def power_on(self) -> None:
        self._powered = True
        # Simulate modem boot time
        await asyncio.sleep(0.1)

    async def power_off(self) -> None:
        self._powered = False

    def is_powered(self) -> bool:
        return self._powered

    async def wait_for_network(self, timeout: float = 60.0) -> bool:
        if not self._powered:
            return False
        # Simulate network registration delay
        await asyncio.sleep(0.1)
        return True

    async def get_network_interface(self) -> str | None:
        if not self._powered:
            return None
        return "usb0"

    async def get_signal_info(self) -> dict:
        if not self._powered:
            return {
                "lte_signal_strength": None,
                "lte_signal_quality": None,
            }
        return {
            "lte_signal_strength": random.randint(-110, -60),
            "lte_signal_quality": random.randint(-20, -3),
        }
