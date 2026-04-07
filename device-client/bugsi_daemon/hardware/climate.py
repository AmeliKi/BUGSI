"""Zigbee climate sensor driver via zigpy + bellows (direct EZSP communication).

Uses zigpy's ControllerApplication to talk directly to the Zigbee coordinator
USB dongle.  No external processes (zigbee2mqtt, mosquitto) are needed.
USB dongle power control via uhubctl.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

from bugsi_daemon.hardware.base import HardwareSensor, PowerControllable

logger = logging.getLogger(__name__)

_USB_CACHE_PATH = Path("/var/cache/bugsi/zigbee_usb.json")
_NAME_MAP_PATH = Path("/var/cache/bugsi/zigbee_names.json")

# Known Zigbee dongle USB vendor:product IDs (for uhubctl detection)
_ZIGBEE_VID_PIDS = {"10c4:ea60", "1a86:55d4", "1cf1:0030", "0451:16a8"}

# Serial port patterns for auto-detection
_SERIAL_PATTERNS = ("*Sonoff*Zigbee*", "*10c4*")

# zigpy connection retry settings (for transient USB serial errors)
_ZIGPY_RETRY_MAX_ATTEMPTS = 3
_ZIGPY_RETRY_BASE_DELAY = 2.0
_ZIGPY_RETRY_BACKOFF_FACTOR = 2.0

# ZCL cluster IDs
_CLUSTER_TEMPERATURE = 0x0402
_CLUSTER_HUMIDITY = 0x0405
_CLUSTER_POWER_CONFIG = 0x0001
_CLUSTER_TUYA = 0xEF00

# ZCL attribute IDs
_ATTR_MEASURED_VALUE = 0x0000
_ATTR_BATTERY_PERCENT = 0x0021
_ATTR_BATTERY_VOLTAGE = 0x0020

# Tuya datapoint IDs (common for TZE200/TZE204 temperature+humidity sensors)
_TUYA_DP_TEMPERATURE = 18
_TUYA_DP_HUMIDITY = 19
_TUYA_DP_BATTERY = 21
# Alternative DP IDs used by some models
_TUYA_DP_TEMPERATURE_ALT = 1
_TUYA_DP_HUMIDITY_ALT = 2
_TUYA_DP_BATTERY_ALT = 4


class _SerializableBytes:
    """Wraps raw bytes with a .serialize() method for zigpy cluster.request()."""

    def __init__(self, data: bytes):
        self._data = data

    def serialize(self) -> bytes:
        return self._data


class _ClimateClusterListener:
    """Receives ZCL attribute reports and updates the sensor's last_reading."""

    def __init__(self, sensor: ZigbeeClimateSensor, cluster_id: int) -> None:
        self._sensor = sensor
        self._cluster_id = cluster_id

    def attribute_updated(self, attrid: int, value, timestamp=None) -> None:
        """Called by zigpy when a ZCL attribute report arrives."""
        try:
            if self._cluster_id == _CLUSTER_TEMPERATURE and attrid == _ATTR_MEASURED_VALUE:
                self._sensor._last_reading["temperature"] = round(value / 100.0, 1)
            elif self._cluster_id == _CLUSTER_HUMIDITY and attrid == _ATTR_MEASURED_VALUE:
                self._sensor._last_reading["humidity"] = round(value / 100.0, 1)
            elif self._cluster_id == _CLUSTER_POWER_CONFIG:
                if attrid == _ATTR_BATTERY_PERCENT:
                    self._sensor._last_reading["sensor_battery"] = int(value / 2)
                elif attrid == _ATTR_BATTERY_VOLTAGE:
                    self._sensor._last_reading["sensor_voltage"] = int(value * 100)
            logger.debug("ZCL attribute update: cluster=0x%04x attr=0x%04x value=%s",
                         self._cluster_id, attrid, value)
            self._sensor._data_event.set()
        except (TypeError, ValueError):
            logger.debug("Ignoring invalid ZCL attribute value: %s", value)

    def cluster_command(self, tsn, command_id, args):
        pass

    def zdo_command(self, *args, **kwargs):
        pass


class _TuyaClusterListener:
    """Receives Tuya DP reports on cluster 0xEF00 and updates the sensor's last_reading.

    Tuya TS0601 devices send all data through a proprietary cluster (0xEF00)
    using datapoints (DPs) rather than standard ZCL attribute reports.

    Tuya protocol commands:
      0x01 — Set Data (coordinator → device)
      0x02 — Data Report (device → coordinator, contains DPs)
      0x03 — DP Query (coordinator → device, requests all DPs)
      0x10 — MCU version query (coordinator → device)
      0x11 — MCU version report (device → coordinator)
      0x24 — Time sync (bidirectional)
    """

    # Commands that carry DP data
    _DP_COMMANDS = {0x01, 0x02}
    _CMD_TIME_SYNC = 0x24
    _CMD_MCU_VERSION = 0x11
    _CMD_DP_QUERY = 0x03

    def __init__(self, sensor: ZigbeeClimateSensor, cluster=None) -> None:
        self._sensor = sensor
        self._cluster = cluster
        self._seq = 0
        self._data_received = False

    def _next_seq(self) -> int:
        self._seq = (self._seq + 1) & 0xFFFF
        return self._seq

    def cluster_command(self, tsn, command_id, args) -> None:
        """Called by zigpy when a Tuya cluster command arrives."""
        try:
            raw = self._to_bytes(args)
            if raw is None:
                logger.info("Tuya 0xEF00: cmd=0x%02x args_type=%s", command_id, type(args).__name__)
                return

            logger.info("Tuya 0xEF00: cmd=0x%02x len=%d data=%s", command_id, len(raw), raw.hex())

            if command_id in self._DP_COMMANDS:
                self._parse_tuya_payload(raw)
            elif command_id == self._CMD_TIME_SYNC:
                logger.info("Tuya time sync request, sending response")
                asyncio.ensure_future(self._respond_time_sync(tsn))
            elif command_id == self._CMD_MCU_VERSION:
                logger.info("Tuya MCU version report: %s", raw.hex())
            else:
                logger.info("Tuya 0xEF00: unhandled cmd=0x%02x", command_id)

            # Device is awake right now — opportunistically query DPs if needed
            if not self._data_received:
                asyncio.ensure_future(self._query_dp_values())
        except Exception:
            logger.warning("Error parsing Tuya cluster command", exc_info=True)

    async def _respond_time_sync(self, tsn: int) -> None:
        """Send time sync response (cmd 0x24) with current UTC time."""
        if self._cluster is None:
            return
        try:
            import time as _time
            # Tuya time is seconds since 2000-01-01 00:00:00 UTC
            utc_now = int(_time.time())
            tuya_utc = utc_now - 946684800  # epoch diff: 2000-01-01 vs 1970-01-01
            local_now = utc_now + _time.timezone * (-1 if _time.daylight else 1)
            tuya_local = local_now - 946684800

            payload = tuya_utc.to_bytes(4, "big") + tuya_local.to_bytes(4, "big")
            await self._cluster.request(
                False, self._CMD_TIME_SYNC, _SerializableBytes, payload, tsn=tsn,
                expect_reply=False,
            )
            logger.info("Tuya time sync response sent")
        except Exception:
            logger.debug("Failed to send Tuya time sync response", exc_info=True)

    async def _query_dp_values(self) -> None:
        """Send DP query (cmd 0x03) to request the device to report all DPs."""
        if self._cluster is None:
            return
        try:
            seq = self._next_seq()
            payload = seq.to_bytes(2, "big")
            await self._cluster.request(
                False, self._CMD_DP_QUERY, _SerializableBytes, payload,
                expect_reply=False,
            )
            logger.info("Tuya DP query sent (requesting all datapoints)")
        except Exception:
            logger.info("Failed to send Tuya DP query", exc_info=True)

    @staticmethod
    def _to_bytes(args) -> bytes | None:
        """Convert various args formats to bytes."""
        if isinstance(args, (bytes, bytearray)):
            return bytes(args)
        # zigpy may use custom bytes-like types (SerializableBytes, etc.)
        if hasattr(args, '__bytes__'):
            return bytes(args)
        if isinstance(args, (list, tuple)):
            if len(args) >= 1 and isinstance(args[0], (bytes, bytearray)):
                return bytes(args[0])
            # Try converting list of ints to bytes
            try:
                return bytes(args)
            except (TypeError, ValueError):
                pass
        # Last resort: try bytes() conversion
        try:
            return bytes(args)
        except (TypeError, ValueError):
            return None

    def _parse_tuya_payload(self, data: bytes) -> None:
        """Parse one or more Tuya DPs from a payload.

        Tuya frame format (after ZCL header):
          [seq_num: 2 bytes][dp_id: 1][dp_type: 1][dp_len: 2 BE][dp_value: dp_len bytes]
        Some devices add a status byte before seq_num.
        We try multiple header offsets to handle variants.
        """
        for header_skip in (2, 0, 1, 3):
            if self._try_parse_dps(data, header_skip):
                return
        logger.warning("Tuya: could not parse DPs from payload: %s", data.hex())

    def _try_parse_dps(self, data: bytes, header_skip: int) -> bool:
        """Try to parse DPs starting at the given offset. Returns True if any DP was found."""
        offset = header_skip
        found_any = False
        while offset + 4 <= len(data):
            dp_id = data[offset]
            dp_type = data[offset + 1]
            dp_len = int.from_bytes(data[offset + 2:offset + 4], "big")
            if dp_len > 32 or offset + 4 + dp_len > len(data):
                # dp_len too large or exceeds payload — wrong offset
                return found_any
            dp_raw = data[offset + 4:offset + 4 + dp_len]
            offset += 4 + dp_len

            value = self._decode_dp_value(dp_type, dp_raw)
            logger.info("Tuya DP %d (type=%d len=%d): value=%s", dp_id, dp_type, dp_len, value)
            if value is not None:
                self._apply_dp(dp_id, value)
                found_any = True
        return found_any

    @staticmethod
    def _decode_dp_value(dp_type: int, raw: bytes):
        """Decode a Tuya DP value based on its type."""
        if dp_type == 2 and len(raw) == 4:  # value (signed 32-bit)
            return int.from_bytes(raw, "big", signed=True)
        if dp_type == 2 and len(raw) == 2:  # some devices use 16-bit
            return int.from_bytes(raw, "big", signed=True)
        if dp_type == 1 and len(raw) == 1:  # bool
            return raw[0]
        if dp_type == 4 and len(raw) == 1:  # enum
            return raw[0]
        return None

    def _apply_dp(self, dp_id: int, value: int) -> None:
        """Map a Tuya DP value to the sensor reading dict."""
        if dp_id in (_TUYA_DP_TEMPERATURE, _TUYA_DP_TEMPERATURE_ALT):
            self._sensor._last_reading["temperature"] = round(value / 10.0, 1)
            self._sensor._data_event.set()
        elif dp_id in (_TUYA_DP_HUMIDITY, _TUYA_DP_HUMIDITY_ALT):
            self._sensor._last_reading["humidity"] = round(value, 1)
            self._sensor._data_event.set()
        elif dp_id in (_TUYA_DP_BATTERY, _TUYA_DP_BATTERY_ALT):
            self._sensor._last_reading["sensor_battery"] = int(value)
            self._sensor._data_event.set()
        # Stop retrying once we have both temperature and humidity
        reading = self._sensor._last_reading
        if "temperature" in reading and "humidity" in reading:
            self._data_received = True

    def attribute_updated(self, attrid: int, value, timestamp=None) -> None:
        """Some Tuya devices also send standard attribute updates."""
        logger.debug("Tuya attribute update: attr=0x%04x value=%s", attrid, value)

    def zdo_command(self, *args, **kwargs):
        pass


class _DeviceJoinListener:
    """Temporary listener attached to the zigpy app during pairing."""

    def __init__(self) -> None:
        self.joined: list[dict] = []
        self._callbacks: list = []
        self._event = asyncio.Event()

    def device_joined(self, device) -> None:
        data = {
            "friendly_name": str(device.ieee),
            "ieee_address": str(device.ieee),
            "model": getattr(device, "model", "?") or "?",
            "vendor": getattr(device, "manufacturer", "?") or "?",
        }
        self.joined.append(data)
        for cb in self._callbacks:
            cb(data)
        self._event.set()


class _AppDeviceListener:
    """Permanent app-level listener that installs cluster listeners when
    a device joins or completes initialization.

    For sleepy end devices, the full zigpy interview can take minutes.
    This listener monitors newly-joined devices and installs cluster listeners
    as soon as the endpoint's clusters become available (before the full
    interview completes), then actively reads attribute values.
    """

    _CLIMATE_CLUSTERS = {_CLUSTER_TEMPERATURE, _CLUSTER_HUMIDITY, _CLUSTER_POWER_CONFIG, _CLUSTER_TUYA}

    def __init__(self, sensor: ZigbeeClimateSensor) -> None:
        self._sensor = sensor
        self._monitor_tasks: list[asyncio.Task] = []

    def device_initialized(self, device, *, new: bool = True) -> None:
        """Called by zigpy when a device finishes its interview."""
        if self._has_climate_clusters(device):
            logger.info("Device %s initialized with climate clusters, installing listeners",
                        device.ieee)
            self._sensor._install_listeners_for_device(device)

    def device_joined(self, device) -> None:
        """Called by zigpy when a new device joins — start monitoring for clusters."""
        logger.info("Device %s joined, monitoring for climate clusters...", device.ieee)
        task = asyncio.ensure_future(self._monitor_device(device))
        self._monitor_tasks.append(task)

    async def _monitor_device(self, device, poll_interval: float = 2.0, max_wait: float = 120.0) -> None:
        """Poll a newly-joined device until its climate clusters appear, then
        install listeners and actively read attributes."""
        elapsed = 0.0
        while elapsed < max_wait:
            if self._has_climate_clusters(device):
                logger.info("Device %s clusters available, installing listeners", device.ieee)
                self._sensor._install_listeners_for_device(device)
                await self._read_attributes(device)
                return
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
        logger.debug("Device %s: climate clusters not found after %.0fs", device.ieee, max_wait)

    async def _read_attributes(self, device) -> None:
        """Actively read current temperature/humidity/battery from the device."""
        read_targets = [
            (_CLUSTER_TEMPERATURE, [_ATTR_MEASURED_VALUE]),
            (_CLUSTER_HUMIDITY, [_ATTR_MEASURED_VALUE]),
            (_CLUSTER_POWER_CONFIG, [_ATTR_BATTERY_PERCENT, _ATTR_BATTERY_VOLTAGE]),
        ]
        for ep_id, endpoint in device.endpoints.items():
            if ep_id == 0 or not hasattr(endpoint, "in_clusters"):
                continue
            for cluster_id, attrs in read_targets:
                if cluster_id in endpoint.in_clusters:
                    cluster = endpoint.in_clusters[cluster_id]
                    try:
                        result = await cluster.read_attributes(attrs)
                        logger.debug("Read attributes from cluster 0x%04x: %s", cluster_id, result)
                    except Exception:
                        logger.debug("Could not read cluster 0x%04x on %s",
                                     cluster_id, device.ieee, exc_info=True)

    @classmethod
    def _has_climate_clusters(cls, device) -> bool:
        for ep_id, endpoint in device.endpoints.items():
            if ep_id == 0:
                continue
            if hasattr(endpoint, "in_clusters"):
                if cls._CLIMATE_CLUSTERS & set(endpoint.in_clusters):
                    return True
        return False


class ZigbeeClimateSensor(HardwareSensor, PowerControllable):
    """Zigbee climate sensor via zigpy + bellows (direct EZSP)."""

    def __init__(
        self,
        serial_port: str = "auto",
        adapter: str = "ezsp",
        device_name: str = "climate_sensor",
        database_path: str = "/var/cache/bugsi/zigbee.db",
        network_channel: int = 11,
        usb_hub: str | None = None,
        usb_port: str | None = None,
    ) -> None:
        self._serial_port = serial_port
        self._adapter = adapter
        self._device_name = device_name
        self._database_path = Path(database_path)
        self._network_channel = network_channel
        self._usb_hub = usb_hub
        self._usb_port = usb_port
        self._powered = False
        self._healthy = False
        self._last_reading: dict = {}
        self._data_event = asyncio.Event()
        self._app = None  # zigpy ControllerApplication

    async def initialize(self) -> None:
        try:
            import zigpy.application  # noqa: F401
            import bellows.zigbee.application  # noqa: F401
        except ImportError:
            raise NotImplementedError(
                "zigpy/bellows not available — install them: pip install zigpy bellows"
            )

    async def read(self) -> dict:
        return self._last_reading

    async def wait_for_reading(self, timeout: float = 30.0) -> dict:
        """Wait until temperature and humidity are available, or timeout."""
        import time as _time
        deadline = _time.monotonic() + timeout
        while _time.monotonic() < deadline:
            remaining = deadline - _time.monotonic()
            if remaining <= 0:
                break
            self._data_event.clear()
            try:
                await asyncio.wait_for(self._data_event.wait(), timeout=remaining)
            except asyncio.TimeoutError:
                break
            # Got some data — check if we have both temperature and humidity
            if "temperature" in self._last_reading and "humidity" in self._last_reading:
                return self._last_reading
        return self._last_reading

    async def shutdown(self) -> None:
        if self._app is not None:
            try:
                await self._app.shutdown()
            except Exception:
                logger.debug("zigpy shutdown error", exc_info=True)
            self._app = None
        self._healthy = False

    def is_healthy(self) -> bool:
        return self._healthy and self._powered

    async def power_on(self) -> None:
        if self._powered:
            return

        # Power on USB dongle via uhubctl
        await self._uhubctl_power("on")

        # Wait for USB device to enumerate
        await asyncio.sleep(2)

        # Resolve serial port
        resolved_port = self._serial_port
        if resolved_port == "auto":
            resolved_port = self._auto_detect_serial_port()
            if resolved_port is None:
                logger.warning("Could not auto-detect Zigbee serial port, trying /dev/ttyUSB0")
                resolved_port = "/dev/ttyUSB0"
            else:
                logger.info("Auto-detected Zigbee coordinator at %s", resolved_port)

        # Start zigpy controller
        try:
            await self._start_zigpy(resolved_port)
        except Exception:
            logger.exception("Failed to start zigpy controller")
            self._healthy = False
            self._powered = True  # USB dongle is on, even if zigpy failed
            raise

        self._powered = True
        self._healthy = True
        logger.info("Zigbee powered on (USB dongle + zigpy controller)")

        # Listen for devices that join/initialize after power-on
        if self._app is not None:
            self._app.add_listener(_AppDeviceListener(self))

        # Install listeners on target device if already paired
        self._install_listeners_on_target()

    async def power_off(self) -> None:
        if not self._powered:
            return

        # Suppress CancelledError/KeyError logs from zigpy and asyncio during
        # the entire shutdown sequence. Cancelled tasks from sleepy device
        # communication can log errors many event loop ticks after shutdown().
        suppressed_loggers = ["zigpy.zcl", "asyncio"]
        prev_levels = {}
        for name in suppressed_loggers:
            lg = logging.getLogger(name)
            prev_levels[name] = lg.level
            lg.setLevel(logging.CRITICAL)

        try:
            if self._app is not None:
                try:
                    await self._app.shutdown()
                except Exception:
                    logger.debug("zigpy shutdown error", exc_info=True)
                self._app = None

            # Power off USB dongle via uhubctl
            await self._uhubctl_power("off")

            self._powered = False
            self._healthy = False
            logger.info("Zigbee powered off (USB dongle + zigpy controller)")

            # Let cancelled task callbacks drain before restoring loggers
            await asyncio.sleep(0.5)
        finally:
            for name, level in prev_levels.items():
                logging.getLogger(name).setLevel(level)

    def is_powered(self) -> bool:
        return self._powered

    async def get_devices(self) -> list[dict]:
        if not self._powered or self._app is None:
            return []

        name_map = self._load_name_map()
        devices = []
        for ieee, dev in self._app.devices.items():
            ieee_str = str(ieee)
            friendly = name_map.get(ieee_str, ieee_str)
            model = getattr(dev, "model", None) or "?"
            manufacturer = getattr(dev, "manufacturer", None) or "?"
            is_coordinator = False
            if hasattr(dev, "node_desc") and dev.node_desc is not None:
                is_coordinator = dev.node_desc.is_coordinator
            devices.append({
                "friendly_name": friendly,
                "ieee_address": ieee_str,
                "type": "Coordinator" if is_coordinator else "EndDevice",
                "model": model,
                "vendor": manufacturer,
                "available": dev.last_seen is not None,
            })
        return devices

    async def pair_zigbee(
        self,
        timeout: int = 120,
        on_device_joined=None,
    ) -> list[dict]:
        if not self._powered or self._app is None:
            raise RuntimeError("Zigbee stack must be powered on before pairing")

        join_listener = _DeviceJoinListener()
        if on_device_joined:
            join_listener._callbacks.append(on_device_joined)

        self._app.listener_event = lambda name, *args: (
            getattr(join_listener, name, lambda *a: None)(*args)
        )
        original_listener = None
        try:
            # Register listener for device_joined events
            self._app.add_listener(join_listener)

            await self._app.permit(time_s=timeout)
            logger.info("Pairing window open for %ds", timeout)

            try:
                async with asyncio.timeout(timeout):
                    while True:
                        join_listener._event.clear()
                        await join_listener._event.wait()
                        # Check if the device has completed its interview
                        for j in join_listener.joined:
                            ieee_str = j["ieee_address"]
                            for ieee, dev in self._app.devices.items():
                                if str(ieee) == ieee_str and dev.endpoints:
                                    # Save name mapping
                                    name_map = self._load_name_map()
                                    name_map[ieee_str] = ieee_str  # default to IEEE
                                    self._save_name_map(name_map)
                                    # Install listeners
                                    self._install_listeners_for_device(dev)
                                    # Try to configure reporting
                                    try:
                                        await self._configure_reporting(dev)
                                    except Exception:
                                        logger.debug("Could not configure reporting", exc_info=True)
                                    break
            except asyncio.TimeoutError:
                pass

            # Disable permit join
            try:
                await self._app.permit(time_s=0)
                logger.info("Permit join disabled")
            except Exception:
                logger.debug("Could not disable permit join", exc_info=True)
        finally:
            try:
                self._app.remove_listener(join_listener)
            except (ValueError, AttributeError):
                pass

        return join_listener.joined

    async def rename_device(self, old_name: str, new_name: str) -> bool:
        if not self._powered:
            raise RuntimeError("Zigbee stack must be powered on to rename devices")

        name_map = self._load_name_map()

        # Find IEEE for old_name
        target_ieee = None
        for ieee, name in name_map.items():
            if name == old_name:
                target_ieee = ieee
                break

        if target_ieee is None:
            # Try matching by IEEE directly
            if old_name in name_map:
                target_ieee = old_name
            else:
                logger.warning("Device '%s' not found in name map", old_name)
                return False

        name_map[target_ieee] = new_name
        self._save_name_map(name_map)
        logger.info("Renamed device %s: '%s' -> '%s'", target_ieee, old_name, new_name)
        return True

    # --- zigpy controller management ---

    async def _start_zigpy(self, serial_port: str) -> None:
        """Create and start the zigpy ControllerApplication.

        Retries with exponential backoff on transient connection errors
        (e.g. BrokenPipeError when the USB serial device isn't ready).
        """
        from bellows.zigbee.application import ControllerApplication

        try:
            from zigpy.exceptions import TransientConnectionError
        except ImportError:
            TransientConnectionError = None

        retryable = (OSError,)
        if TransientConnectionError is not None:
            retryable = (OSError, TransientConnectionError)

        self._database_path.parent.mkdir(parents=True, exist_ok=True)

        zigpy_config = {
            "database_path": str(self._database_path),
            "device": {
                "path": serial_port,
            },
            "network": {
                "channel": self._network_channel,
            },
        }

        last_exc: Exception | None = None
        delay = _ZIGPY_RETRY_BASE_DELAY
        for attempt in range(1, _ZIGPY_RETRY_MAX_ATTEMPTS + 1):
            try:
                self._app = await ControllerApplication.new(
                    zigpy_config, auto_form=True,
                )
                logger.info("zigpy controller started (channel %d, db %s)",
                            self._network_channel, self._database_path)
                return
            except retryable as exc:
                last_exc = exc
                if attempt < _ZIGPY_RETRY_MAX_ATTEMPTS:
                    logger.warning(
                        "zigpy connection attempt %d/%d failed (%s), "
                        "retrying in %.1fs",
                        attempt, _ZIGPY_RETRY_MAX_ATTEMPTS, exc, delay,
                    )
                    await asyncio.sleep(delay)
                    delay *= _ZIGPY_RETRY_BACKOFF_FACTOR
                else:
                    logger.error(
                        "zigpy connection failed after %d attempts",
                        _ZIGPY_RETRY_MAX_ATTEMPTS,
                    )
        raise last_exc

    # --- ZCL listener management ---

    def _install_listeners_on_target(self) -> None:
        """Find the target device by name and install cluster listeners."""
        if self._app is None:
            return

        name_map = self._load_name_map()
        target_ieee = None
        for ieee, name in name_map.items():
            if name == self._device_name:
                target_ieee = ieee
                break

        if target_ieee is None:
            logger.debug("Target device '%s' not found in name map", self._device_name)
            return

        for ieee, dev in self._app.devices.items():
            if str(ieee) == target_ieee:
                self._install_listeners_for_device(dev)
                # Update link quality
                if hasattr(dev, "lqi") and dev.lqi is not None:
                    self._last_reading["zigbee_linkquality"] = dev.lqi
                break

    def _install_listeners_for_device(self, device) -> None:
        """Attach ClusterListener instances to a device's relevant clusters."""
        target_clusters = {_CLUSTER_TEMPERATURE, _CLUSTER_HUMIDITY, _CLUSTER_POWER_CONFIG}

        for ep_id, endpoint in device.endpoints.items():
            if ep_id == 0:  # ZDO endpoint
                continue
            if not hasattr(endpoint, "in_clusters"):
                continue
            for cluster_id in target_clusters:
                if cluster_id in endpoint.in_clusters:
                    cluster = endpoint.in_clusters[cluster_id]
                    listener = _ClimateClusterListener(self, cluster_id)
                    cluster.add_listener(listener)
                    logger.debug("Installed listener on endpoint %d cluster 0x%04x",
                                 ep_id, cluster_id)
            # Tuya devices use cluster 0xEF00 for all data
            if _CLUSTER_TUYA in endpoint.in_clusters:
                tuya_cluster = endpoint.in_clusters[_CLUSTER_TUYA]
                listener = _TuyaClusterListener(self, cluster=tuya_cluster)
                tuya_cluster.add_listener(listener)
                logger.info("Installed Tuya listener on endpoint %d cluster 0xEF00", ep_id)

    async def _configure_reporting(self, device) -> None:
        """Configure ZCL attribute reporting for temperature, humidity, battery."""
        reporting_configs = [
            (_CLUSTER_TEMPERATURE, _ATTR_MEASURED_VALUE, 30, 600, 10),   # 0.1°C change
            (_CLUSTER_HUMIDITY, _ATTR_MEASURED_VALUE, 30, 600, 100),     # 1% change
            (_CLUSTER_POWER_CONFIG, _ATTR_BATTERY_PERCENT, 3600, 43200, 2),  # 1% change
        ]

        for ep_id, endpoint in device.endpoints.items():
            if ep_id == 0:
                continue
            if not hasattr(endpoint, "in_clusters"):
                continue
            for cluster_id, attr_id, min_interval, max_interval, change in reporting_configs:
                if cluster_id in endpoint.in_clusters:
                    cluster = endpoint.in_clusters[cluster_id]
                    try:
                        await cluster.configure_reporting(
                            attr_id, min_interval, max_interval, change
                        )
                        logger.debug("Configured reporting: cluster=0x%04x attr=0x%04x",
                                     cluster_id, attr_id)
                    except Exception:
                        logger.debug("Failed to configure reporting for cluster 0x%04x",
                                     cluster_id, exc_info=True)

    # --- Serial port auto-detection ---

    @staticmethod
    def _auto_detect_serial_port() -> str | None:
        """Scan /dev/serial/by-id/ for known Zigbee coordinator patterns."""
        serial_dir = Path("/dev/serial/by-id")
        if not serial_dir.is_dir():
            return None

        try:
            for entry in sorted(serial_dir.iterdir()):
                name = entry.name.lower()
                if "sonoff" in name and "zigbee" in name:
                    return str(entry.resolve())
                if "10c4" in name:
                    return str(entry.resolve())
        except OSError:
            pass

        # Fallback: check if /dev/ttyUSB0 exists
        if Path("/dev/ttyUSB0").exists():
            return "/dev/ttyUSB0"

        return None

    # --- Friendly name mapping ---

    @staticmethod
    def _load_name_map() -> dict[str, str]:
        """Load IEEE -> friendly_name mapping from JSON file."""
        try:
            return json.loads(_NAME_MAP_PATH.read_text())
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}

    @staticmethod
    def _save_name_map(name_map: dict[str, str]) -> None:
        """Persist IEEE -> friendly_name mapping to JSON file."""
        try:
            _NAME_MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
            _NAME_MAP_PATH.write_text(json.dumps(name_map, indent=2))
        except OSError:
            logger.debug("Could not write name map to %s", _NAME_MAP_PATH)

    # --- USB power management (unchanged from original) ---

    async def _parse_uhubctl_output(self, stdout: str) -> tuple[list[str], str | None, str | None]:
        """Parse uhubctl output. Returns (hub_locations, detected_hub, detected_port).

        hub_locations: all hub location strings found in the output.
        detected_hub/port: the hub/port where a Zigbee dongle was found, or None.
        """
        hubs: list[str] = []
        detected_hub = None
        detected_port = None
        current_hub = None

        for line in stdout.splitlines():
            if line.startswith("Current status for hub"):
                parts = line.split()
                try:
                    hub_idx = parts.index("hub") + 1
                    current_hub = parts[hub_idx]
                    hubs.append(current_hub)
                except (ValueError, IndexError):
                    current_hub = None
            elif current_hub and line.strip().startswith("Port "):
                bracket_content = ""
                if "[" in line:
                    bracket_content = line[line.index("["):]
                if any(vid in bracket_content for vid in _ZIGBEE_VID_PIDS) or "Zigbee" in bracket_content:
                    port = line.strip().split(":")[0].replace("Port ", "").strip()
                    detected_hub = current_hub
                    detected_port = port

        return hubs, detected_hub, detected_port

    @staticmethod
    def _load_usb_cache() -> tuple[str | None, str | None]:
        """Load cached USB hub/port from disk."""
        try:
            data = json.loads(_USB_CACHE_PATH.read_text())
            hub = data.get("usb_hub")
            port = data.get("usb_port")
            if hub and port:
                return str(hub), str(port)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass
        return None, None

    @staticmethod
    def _save_usb_cache(hub: str, port: str) -> None:
        """Persist detected USB hub/port to disk."""
        try:
            _USB_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            _USB_CACHE_PATH.write_text(json.dumps({"usb_hub": hub, "usb_port": port}))
        except OSError:
            logger.debug("Could not write USB cache to %s", _USB_CACHE_PATH)

    async def _auto_detect_zigbee_usb(self) -> None:
        """Auto-detect Zigbee USB dongle hub and port via uhubctl."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "uhubctl",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode != 0:
                return

            _, hub, port = await self._parse_uhubctl_output(stdout.decode())
            if hub and port:
                self._usb_hub = hub
                self._usb_port = port
                self._save_usb_cache(hub, port)
                logger.info(
                    "Auto-detected Zigbee USB dongle at hub %s port %s", hub, port,
                )
            else:
                logger.debug("Zigbee USB dongle not visible in uhubctl output (may be powered off)")
        except FileNotFoundError:
            logger.warning("uhubctl not installed — cannot auto-detect Zigbee USB dongle")
        except Exception:
            logger.debug("Zigbee USB auto-detect failed", exc_info=True)

    async def _uhubctl_power(self, action: str) -> None:
        """Control USB hub port power via uhubctl."""
        # Auto-detect hub/port if not configured
        if self._usb_hub is None or self._usb_port is None:
            await self._auto_detect_zigbee_usb()

        # Try cached hub/port from a previous detection
        if self._usb_hub is None or self._usb_port is None:
            cached_hub, cached_port = self._load_usb_cache()
            if cached_hub and cached_port:
                self._usb_hub = cached_hub
                self._usb_port = cached_port
                logger.info("Using cached Zigbee USB location: hub %s port %s", cached_hub, cached_port)

        # If still unknown and powering ON, try all hubs to find the dongle
        if self._usb_hub is None:
            if action == "on":
                await self._uhubctl_power_all_hubs("on")
                await asyncio.sleep(1)
                await self._auto_detect_zigbee_usb()
            else:
                # Never power off all hubs — that kills cameras, storage, etc.
                logger.warning(
                    "Skipping USB power-off: Zigbee dongle hub/port unknown "
                    "(cannot safely power off without affecting other devices)"
                )
            return

        cmd = ["uhubctl", "-a", action, "-l", str(self._usb_hub), "-p", str(self._usb_port)]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.warning(
                "uhubctl %s failed (rc=%d): %s",
                action, proc.returncode, stderr.decode().strip(),
            )
        else:
            logger.info("uhubctl USB power %s (hub %s port %s)", action, self._usb_hub, self._usb_port)

    async def _uhubctl_power_all_hubs(self, action: str) -> None:
        """Power on/off each hub individually (fallback when hub/port unknown)."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "uhubctl",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            hubs, _, _ = await self._parse_uhubctl_output(stdout.decode())

            if not hubs:
                logger.warning("No USB hubs found by uhubctl")
                return

            logger.info("Zigbee USB dongle not detected, powering %s all %d hub(s)", action, len(hubs))
            for hub in hubs:
                p = await asyncio.create_subprocess_exec(
                    "uhubctl", "-a", action, "-l", hub,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await p.communicate()
        except FileNotFoundError:
            pass
        except Exception:
            logger.debug("uhubctl power all hubs failed", exc_info=True)
