import random

from bugsi_daemon.hardware.base import HardwareSensor


class MockStorage(HardwareSensor):
    """Mock USB stick storage monitor."""

    def __init__(self, total_mb: int = 64000):
        self._healthy = True
        self._total_mb = total_mb
        self._used_mb = random.randint(100, total_mb // 4)

    async def initialize(self) -> None:
        self._healthy = True

    async def read(self) -> dict:
        # Simulate slow storage growth
        self._used_mb = min(self._total_mb, self._used_mb + random.randint(0, 10))
        return {
            "storage_used_mb": self._used_mb,
            "storage_total_mb": self._total_mb,
        }

    async def shutdown(self) -> None:
        self._healthy = False

    def is_healthy(self) -> bool:
        return self._healthy
