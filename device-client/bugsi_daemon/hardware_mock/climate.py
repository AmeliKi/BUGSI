import random

from bugsi_daemon.hardware.base import HardwareSensor


class MockClimate(HardwareSensor):
    """Mock SONOFF SNZB-02WD Zigbee temp/humidity sensor."""

    def __init__(self):
        self._healthy = True
        self._base_temp = random.uniform(15.0, 25.0)
        self._base_humidity = random.uniform(45.0, 65.0)

    async def initialize(self) -> None:
        self._healthy = True

    async def read(self) -> dict:
        temp = self._base_temp + random.uniform(-2.0, 2.0)
        humidity = self._base_humidity + random.uniform(-5.0, 5.0)
        return {
            "temperature": round(max(5.0, min(35.0, temp)), 1),
            "humidity": round(max(30.0, min(90.0, humidity)), 1),
        }

    async def shutdown(self) -> None:
        self._healthy = False

    def is_healthy(self) -> bool:
        return self._healthy
