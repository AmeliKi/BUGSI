import logging
import random

from bugsi_daemon.hardware.base import HardwareSensor, PowerControllable

logger = logging.getLogger(__name__)


class MockClimate(HardwareSensor, PowerControllable):
    """Mock Zigbee climate sensor with power control."""

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
            "sensor_battery": random.randint(60, 100),
            "sensor_voltage": random.randint(2800, 3200),
            "zigbee_linkquality": random.randint(50, 255),
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
                "friendly_name": "climate_sensor",
                "type": "EndDevice",
                "model": "SNZB-02D",
                "vendor": "SONOFF",
                "ieee_address": "0x00124b00abcdef01",
                "available": True,
            },
        ]

    async def pair_zigbee(self, timeout: int = 120, on_device_joined=None) -> list[dict]:
        """Simulate a device join event."""
        import asyncio
        await asyncio.sleep(2)
        device = {
            "friendly_name": "0x00124b00abcdef01",
            "ieee_address": "0x00124b00abcdef01",
            "model": "ZTH01",
            "vendor": "Tuya",
        }
        if on_device_joined:
            on_device_joined(device)
        return [device]

    async def rename_device(self, old_name: str, new_name: str) -> bool:
        """Simulate device rename."""
        return True
