import random

from bugsi_daemon.hardware.base import HardwareSensor


class MockBattery(HardwareSensor):
    """Mock Victron SmartShunt returning realistic battery data."""

    def __init__(self):
        self._healthy = True
        self._soc = random.uniform(60.0, 100.0)

    async def initialize(self) -> None:
        self._healthy = True

    async def read(self) -> dict:
        # Simulate slow discharge
        self._soc = max(10.0, self._soc + random.uniform(-0.5, 0.1))
        voltage = 24.0 + (self._soc / 100.0) * 4.0
        current = random.uniform(-2.0, 0.5)
        power = voltage * abs(current)
        consumed_ah = (100.0 - self._soc) / 100.0 * 100.0
        ttg_min = int(self._soc / 100.0 * 4800)

        return {
            "battery_voltage": round(voltage, 2),
            "battery_soc": round(self._soc, 1),
            "battery_current": round(current, 2),
            "battery_power": round(power, 2),
            "battery_consumed_ah": round(consumed_ah, 1),
            "battery_ttg_min": ttg_min,
        }

    async def shutdown(self) -> None:
        self._healthy = False

    def is_healthy(self) -> bool:
        return self._healthy
