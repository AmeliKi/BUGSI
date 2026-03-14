import random
import time

from bugsi_daemon.hardware.base import HardwareSensor


class MockSystem(HardwareSensor):
    """Mock system monitor (CPU temp, uptime)."""

    def __init__(self):
        self._healthy = True
        self._start_time = time.monotonic()

    async def initialize(self) -> None:
        self._healthy = True
        self._start_time = time.monotonic()

    async def read(self) -> dict:
        uptime = int(time.monotonic() - self._start_time)
        return {
            "cpu_temp": round(random.uniform(35.0, 65.0), 1),
            "uptime_seconds": uptime,
        }

    async def shutdown(self) -> None:
        self._healthy = False

    def is_healthy(self) -> bool:
        return self._healthy
