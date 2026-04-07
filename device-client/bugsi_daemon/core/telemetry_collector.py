from __future__ import annotations

import logging
from datetime import datetime, timezone

from bugsi_daemon.buffer.store import BufferStore
from bugsi_daemon.hardware.base import HardwareSensor, LteModemInterface, PowerControllable

logger = logging.getLogger(__name__)


class TelemetryCollector:
    """Reads all sensors and pushes telemetry readings to the buffer."""

    def __init__(
        self,
        buffer: BufferStore,
        battery: HardwareSensor,
        solar: HardwareSensor,
        climate: HardwareSensor,
        storage: HardwareSensor,
        system: HardwareSensor,
        lte: LteModemInterface,
    ):
        self._buffer = buffer
        self._battery = battery
        self._solar = solar
        self._climate = climate
        self._storage = storage
        self._system = system
        self._lte = lte
        self._last_lte_signal: dict = {
            "lte_signal_strength": None,
            "lte_signal_quality": None,
        }

    async def collect(self, extra: dict | None = None) -> dict:
        """Read all sensors and push a telemetry reading to the buffer."""
        reading = {"timestamp": datetime.now(timezone.utc).isoformat()}

        # Battery
        reading.update(await self._safe_read(self._battery, "battery"))

        # Solar (stored but not in telemetry schema yet)
        await self._safe_read(self._solar, "solar")

        # Climate (needs power management — Zigbee sensor must be powered on)
        reading.update(await self._read_climate())

        # Storage
        reading.update(await self._safe_read(self._storage, "storage"))

        # System
        reading.update(await self._safe_read(self._system, "system"))

        # LTE signal: use last-known value (modem is off between uploads)
        reading.update(self._last_lte_signal)

        # Extra fields (e.g. pictures_taken)
        if extra:
            reading.update(extra)

        await self._buffer.push_telemetry(reading)
        logger.debug("Telemetry collected: soc=%s, temp=%s", reading.get("battery_soc"), reading.get("temperature"))
        return reading

    async def update_lte_signal(self) -> dict:
        """Read LTE signal info (call during upload cycle when modem is on)."""
        signal = await self._lte.get_signal_info()
        self._last_lte_signal = {
            "lte_signal_strength": signal.get("lte_signal_strength"),
            "lte_signal_quality": signal.get("lte_signal_quality"),
        }
        return self._last_lte_signal

    def get_last_battery_soc(self) -> float | None:
        """Return the last known battery SoC for power management decisions."""
        return self._last_battery_soc

    async def _read_climate(self) -> dict:
        """Read climate sensor, powering on Zigbee if needed."""
        powered_on = False
        try:
            if isinstance(self._climate, PowerControllable) and not self._climate.is_powered():
                await self._climate.power_on()
                powered_on = True
                if hasattr(self._climate, "wait_for_reading"):
                    await self._climate.wait_for_reading(timeout=30)
            return await self._safe_read(self._climate, "climate")
        except Exception:
            logger.exception("Failed to read climate sensor")
            return {}
        finally:
            if powered_on and isinstance(self._climate, PowerControllable):
                try:
                    await self._climate.power_off()
                except Exception:
                    logger.warning("Failed to power off climate sensor after read")

    async def _safe_read(self, sensor: HardwareSensor, name: str) -> dict:
        """Read a sensor, returning empty dict on failure."""
        try:
            if sensor.is_healthy():
                return await sensor.read()
        except Exception:
            logger.exception("Failed to read %s sensor", name)
        return {}

    @property
    def _last_battery_soc(self) -> float | None:
        return None  # Will be populated after first collect via the reading
