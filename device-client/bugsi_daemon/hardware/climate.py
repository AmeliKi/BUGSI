"""Zigbee climate sensor driver via MQTT and Zigbee2MQTT.

Uses aiomqtt to subscribe to Zigbee2MQTT topics for any paired Zigbee
temperature/humidity sensor. USB dongle power control via uhubctl.
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


class ZigbeeClimateSensor(HardwareSensor, PowerControllable):
    """Zigbee climate sensor via Zigbee2MQTT + MQTT."""

    def __init__(
        self,
        mqtt_host: str = "localhost",
        mqtt_port: int = 1883,
        device_name: str = "climate_sensor",
        usb_hub: str | None = None,
        usb_port: str | None = None,
    ) -> None:
        self._mqtt_host = mqtt_host
        self._mqtt_port = mqtt_port
        self._device_name = device_name
        self._usb_hub = usb_hub
        self._usb_port = usb_port
        self._powered = False
        self._healthy = False
        self._last_reading: dict = {}
        self._mqtt_client = None
        self._listener_task: asyncio.Task | None = None

    async def initialize(self) -> None:
        try:
            import aiomqtt  # noqa: F401
        except ImportError:
            raise NotImplementedError(
                "aiomqtt not available — install it: pip install aiomqtt"
            )
        # Try connecting; if MQTT broker isn't running yet that's OK —
        # power_on() will start mosquitto and reconnect.
        await self._connect_mqtt(log_failure=False)

    async def read(self) -> dict:
        if not self._powered:
            return self._last_reading
        return self._last_reading

    async def shutdown(self) -> None:
        await self._disconnect_mqtt()
        self._healthy = False

    def is_healthy(self) -> bool:
        return self._healthy and self._powered

    async def power_on(self) -> None:
        if self._powered:
            return

        # Power on USB dongle via uhubctl
        await self._uhubctl_power("on")

        # Start services
        await self._systemctl("start", "mosquitto")
        await self._systemctl("start", "zigbee2mqtt")

        self._powered = True
        logger.info("Zigbee powered on (USB dongle + services)")

        # Connect MQTT
        await self._connect_mqtt()

        # Wait for Zigbee2MQTT to finish starting (it needs to initialize
        # the coordinator before it can respond to bridge requests)
        await self._wait_for_zigbee2mqtt()

    async def power_off(self) -> None:
        if not self._powered:
            return

        # Disconnect MQTT
        await self._disconnect_mqtt()

        # Stop services
        await self._systemctl("stop", "zigbee2mqtt")
        await self._systemctl("stop", "mosquitto")

        # Power off USB dongle via uhubctl
        await self._uhubctl_power("off")

        self._powered = False
        self._healthy = False
        logger.info("Zigbee powered off (USB dongle + services)")

    def is_powered(self) -> bool:
        return self._powered

    async def _connect_mqtt(self, log_failure: bool = True) -> None:
        """Connect to MQTT broker and start listener task."""
        import aiomqtt

        try:
            self._mqtt_client = aiomqtt.Client(
                hostname=self._mqtt_host,
                port=self._mqtt_port,
            )
            await self._mqtt_client.__aenter__()
            topic = f"zigbee2mqtt/{self._device_name}"
            await self._mqtt_client.subscribe(topic)
            self._listener_task = asyncio.create_task(self._mqtt_listener())
            self._healthy = True
            logger.info("MQTT connected, subscribed to %s", topic)
        except Exception:
            if log_failure:
                logger.exception("Failed to connect to MQTT broker")
            else:
                logger.debug("MQTT broker not available yet (will connect on power_on)")
            self._healthy = False

    async def _disconnect_mqtt(self) -> None:
        """Stop listener and disconnect MQTT."""
        if self._listener_task and not self._listener_task.done():
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        self._listener_task = None

        if self._mqtt_client:
            try:
                await self._mqtt_client.__aexit__(None, None, None)
            except Exception:
                pass
            self._mqtt_client = None

    async def _mqtt_listener(self) -> None:
        """Background task: consume MQTT messages and update readings."""
        try:
            async for message in self._mqtt_client.messages:
                try:
                    payload = json.loads(message.payload.decode())
                    reading = {}
                    if "temperature" in payload:
                        reading["temperature"] = round(float(payload["temperature"]), 1)
                    if "humidity" in payload:
                        reading["humidity"] = round(float(payload["humidity"]), 1)
                    if "battery" in payload:
                        reading["sensor_battery"] = int(payload["battery"])
                    elif "battery_state" in payload:
                        reading["sensor_battery_state"] = payload["battery_state"]
                    if "voltage" in payload:
                        reading["sensor_voltage"] = int(payload["voltage"])
                    if "linkquality" in payload:
                        reading["zigbee_linkquality"] = int(payload["linkquality"])
                    if reading:
                        self._last_reading = reading
                        logger.debug("Climate update: %s", reading)
                except (json.JSONDecodeError, ValueError):
                    logger.debug("Ignoring non-JSON MQTT message")
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            # Disconnection during shutdown is expected — don't log as error
            if "isconnect" in str(exc):
                logger.debug("MQTT listener stopped (broker disconnected)")
            else:
                logger.exception("MQTT listener failed")
            self._healthy = False

    async def get_devices(self) -> list[dict]:
        """Query Zigbee2MQTT bridge for paired devices.

        Reads the retained ``zigbee2mqtt/bridge/devices`` topic which Z2M
        publishes automatically on startup and after every device change.
        Uses a separate MQTT client to avoid competing with the main
        listener task's message iterator.
        """
        if not self._powered:
            return []

        import aiomqtt

        devices: list[dict] = []
        topic = "zigbee2mqtt/bridge/devices"

        try:
            async with aiomqtt.Client(
                hostname=self._mqtt_host, port=self._mqtt_port,
            ) as client:
                await client.subscribe(topic)

                try:
                    async with asyncio.timeout(10):
                        async for message in client.messages:
                            if str(message.topic) == topic:
                                devices = json.loads(message.payload.decode())
                                break
                except asyncio.TimeoutError:
                    logger.warning("Zigbee2MQTT device list not received (topic: %s)", topic)
        except Exception:
            logger.exception("Failed to query Zigbee2MQTT devices")

        return devices

    async def pair_zigbee(
        self,
        timeout: int = 120,
        on_device_joined=None,
    ) -> list[dict]:
        """Enable Zigbee permit_join and listen for new device joins.

        Uses a separate MQTT client to avoid conflicting with the main
        listener task's message iterator.

        Args:
            timeout: How long to keep permit_join open (seconds).
            on_device_joined: Optional callback invoked for each joined device.

        Returns:
            List of device_joined event payloads received during the window.
        """
        if not self._powered:
            raise RuntimeError("Zigbee stack must be powered on before pairing")

        import aiomqtt

        joined: list[dict] = []
        async with aiomqtt.Client(
            hostname=self._mqtt_host, port=self._mqtt_port,
        ) as client:
            event_topic = "zigbee2mqtt/bridge/event"
            permit_request = "zigbee2mqtt/bridge/request/permit_join"
            permit_response = "zigbee2mqtt/bridge/response/permit_join"

            await client.subscribe(event_topic)
            await client.subscribe(permit_response)

            # Z2M reports "online" before it is ready to handle bridge
            # requests — wait for the startup message flood to settle.
            logger.debug("Waiting 2s for Zigbee2MQTT to finish initializing...")
            await asyncio.sleep(2)

            permit_payload = json.dumps({"value": True, "time": timeout})
            logger.info("Publishing permit_join to %s: %s", permit_request, permit_payload)
            await client.publish(permit_request, permit_payload, qos=1)

            try:
                async with asyncio.timeout(timeout):
                    async for message in client.messages:
                        topic = str(message.topic)
                        raw = message.payload.decode()
                        logger.debug("MQTT message on %s: %s", topic, raw[:200])

                        if topic == permit_response:
                            logger.info("Permit join response: %s", raw[:200])
                            continue

                        if topic != event_topic:
                            continue

                        try:
                            payload = json.loads(raw)
                        except (json.JSONDecodeError, ValueError):
                            continue

                        event_type = payload.get("type")
                        logger.info("Bridge event: %s", event_type)

                        if event_type == "device_joined":
                            data = payload.get("data", {})
                            joined.append(data)
                            if on_device_joined:
                                on_device_joined(data)
                        elif event_type == "device_interview":
                            status = payload.get("data", {}).get("status")
                            if status == "successful" and joined:
                                logger.info("Interview complete, closing pairing window")
                                break
            except asyncio.TimeoutError:
                pass
            finally:
                try:
                    await client.publish(
                        permit_request,
                        json.dumps({"value": False}),
                        qos=1,
                    )
                    logger.info("Permit join disabled")
                except Exception:
                    logger.debug("Could not disable permit join (Z2M may already be stopping)")

        return joined

    async def rename_device(self, old_name: str, new_name: str) -> bool:
        """Rename a Zigbee device's friendly_name via Zigbee2MQTT bridge.

        Uses a separate MQTT client. Returns True if the rename was acknowledged.
        """
        if not self._powered:
            raise RuntimeError("Zigbee stack must be powered on to rename devices")

        import aiomqtt

        request_topic = "zigbee2mqtt/bridge/request/device/rename"
        response_topic = "zigbee2mqtt/bridge/response/device/rename"

        async with aiomqtt.Client(
            hostname=self._mqtt_host, port=self._mqtt_port,
        ) as client:
            await client.subscribe(response_topic)
            await client.publish(
                request_topic,
                json.dumps({"from": old_name, "to": new_name}),
                qos=1,
            )

            try:
                async with asyncio.timeout(5):
                    async for message in client.messages:
                        if str(message.topic) == response_topic:
                            payload = json.loads(message.payload.decode())
                            return payload.get("status") == "ok"
            except asyncio.TimeoutError:
                logger.warning("Device rename request timed out")
                return False

        return False

    async def _wait_for_zigbee2mqtt(self, timeout: float = 30) -> bool:
        """Wait for Zigbee2MQTT to publish its bridge state (= ready).

        Uses a separate MQTT client to avoid competing with the main
        listener task's message iterator.
        Returns True if Zigbee2MQTT became ready, False on timeout.
        """
        import aiomqtt

        state_topic = "zigbee2mqtt/bridge/state"
        logger.info("Waiting up to %.0fs for Zigbee2MQTT to start...", timeout)
        try:
            async with aiomqtt.Client(
                hostname=self._mqtt_host, port=self._mqtt_port,
            ) as client:
                await client.subscribe(state_topic)
                try:
                    async with asyncio.timeout(timeout):
                        async for message in client.messages:
                            if str(message.topic) == state_topic:
                                try:
                                    payload = json.loads(message.payload.decode())
                                    state = payload.get("state", "")
                                except (json.JSONDecodeError, ValueError):
                                    state = message.payload.decode()
                                if state == "online":
                                    logger.info("Zigbee2MQTT bridge state: online")
                                    return True
                                logger.info("Zigbee2MQTT bridge state: %s (waiting for online...)", state)
                except asyncio.TimeoutError:
                    logger.warning(
                        "Zigbee2MQTT did not publish bridge state within %.0fs", timeout,
                    )
                    return False
        except Exception:
            logger.debug("Failed waiting for Zigbee2MQTT bridge state", exc_info=True)
            return False

    async def _parse_uhubctl_output(self, stdout: str) -> tuple[list[str], str | None, str | None]:
        """Parse uhubctl output. Returns (hub_locations, detected_hub, detected_port).

        hub_locations: all hub location strings found in the output.
        detected_hub/port: the hub/port where a Zigbee dongle was found, or None.
        """
        # Known Zigbee dongle USB vendor:product IDs
        zigbee_vid_pids = {"10c4:ea60", "1a86:55d4", "1cf1:0030", "0451:16a8"}

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
                if any(vid in bracket_content for vid in zigbee_vid_pids) or "Zigbee" in bracket_content:
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

        # If still unknown, power on each hub individually, then re-detect
        if self._usb_hub is None:
            await self._uhubctl_power_all_hubs(action)
            if action == "on":
                await asyncio.sleep(1)
                await self._auto_detect_zigbee_usb()
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

    async def _systemctl(self, action: str, service: str) -> None:
        """Start/stop a systemd service."""
        proc = await asyncio.create_subprocess_exec(
            "systemctl", action, service,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.warning(
                "systemctl %s %s failed: %s",
                action, service, stderr.decode().strip(),
            )
        else:
            logger.debug("systemctl %s %s OK", action, service)
