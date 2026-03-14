import random
from datetime import datetime, timezone

from bugsi_daemon.hardware.base import HardwareSensor


class MockSolar(HardwareSensor):
    """Mock Victron SmartSolar MPPT with time-of-day solar curve."""

    def __init__(self):
        self._healthy = True

    async def initialize(self) -> None:
        self._healthy = True

    async def read(self) -> dict:
        hour = datetime.now(timezone.utc).hour
        # Simple solar curve: peak at noon, zero at night
        if 6 <= hour <= 20:
            solar_factor = max(0.0, 1.0 - abs(hour - 13) / 7.0)
        else:
            solar_factor = 0.0

        pv_voltage = round(solar_factor * 44.0 + random.uniform(-1.0, 1.0), 1)
        pv_power = round(solar_factor * 100.0 + random.uniform(-5.0, 5.0), 1)
        charge_current = round(pv_power / 28.0, 2) if pv_power > 0 else 0.0

        return {
            "solar_pv_voltage": max(0.0, pv_voltage),
            "solar_pv_power": max(0.0, pv_power),
            "solar_charge_current": max(0.0, charge_current),
        }

    async def shutdown(self) -> None:
        self._healthy = False

    def is_healthy(self) -> bool:
        return self._healthy
