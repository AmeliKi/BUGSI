import logging
import random

from bugsi_daemon.hardware.base import HardwareSensor, PowerControllable

logger = logging.getLogger(__name__)


class MockClimate(HardwareSensor, PowerControllable):
    """Mock SONOFF SNZB-02WD Zigbee temp/humidity sensor with power control."""

    def __init__(self):
        self._healthy = False
        self._powered = False
        self._base_temp = random.uniform(15.0, 25.0)
        self._base_humidity = random.uniform(45.0, 65.0)
        self._last_reading: dict = {}

    async def initialize(self) -> None:
        self._healthy = True
        self._powered = True

    async def read(self) -> dict:
        if not self._powered:
            return self._last_reading
        temp = self._base_temp + random.uniform(-2.0, 2.0)
        humidity = self._base_humidity + random.uniform(-5.0, 5.0)
        self._last_reading = {
            "temperature": round(max(5.0, min(35.0, temp)), 1),
            "humidity": round(max(30.0, min(90.0, humidity)), 1),
        }
        return self._last_reading

    async def shutdown(self) -> None:
        self._healthy = False
        self._powered = False

    def is_healthy(self) -> bool:
        return self._healthy and self._powered

    async def power_on(self) -> None:
        self._powered = True
        self._healthy = True
        logger.info("MockClimate powered on (Zigbee dongle + services)")

    async def power_off(self) -> None:
        self._powered = False
        self._healthy = False
        logger.info("MockClimate powered off (Zigbee dongle + services)")

    def is_powered(self) -> bool:
        return self._powered

    async def get_devices(self) -> list[dict]:
        """Return a mock device list."""
        if not self._powered:
            return []
        return [
            {
                "friendly_name": "SNZB-02WD",
                "type": "EndDevice",
                "model": "SNZB-02D",
                "vendor": "SONOFF",
                "ieee_address": "0x00124b00abcdef01",
                "available": True,
            },
        ]
