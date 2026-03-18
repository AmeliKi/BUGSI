"""Zigbee climate sensor driver via MQTT and Zigbee2MQTT.

Uses aiomqtt to subscribe to Zigbee2MQTT topics for the SONOFF SNZB-02WD
temperature/humidity sensor. USB dongle power control via uhubctl.
"""
from __future__ import annotations

import asyncio
import json
import logging

from bugsi_daemon.hardware.base import HardwareSensor, PowerControllable

logger = logging.getLogger(__name__)


class ZigbeeClimateSensor(HardwareSensor, PowerControllable):
    """SONOFF SNZB-02WD Zigbee temp/humidity sensor via Zigbee2MQTT + MQTT."""

    def __init__(
        self,
        mqtt_host: str = "localhost",
        mqtt_port: int = 1883,
        device_name: str = "SNZB-02WD",
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
        await self._connect_mqtt()

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

    async def _connect_mqtt(self) -> None:
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
            logger.exception("Failed to connect to MQTT broker")
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
                    if reading:
                        self._last_reading = reading
                        logger.debug("Climate update: %s", reading)
                except (json.JSONDecodeError, ValueError):
                    logger.debug("Ignoring non-JSON MQTT message")
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("MQTT listener failed")
            self._healthy = False

    async def get_devices(self) -> list[dict]:
        """Query Zigbee2MQTT bridge for paired devices and their status.

        Returns a list of dicts with device info (friendly_name, type,
        model, available, etc.).  Requires the Zigbee stack to be powered on.
        """
        if not self._powered or not self._mqtt_client:
            return []

        import aiomqtt

        devices: list[dict] = []
        request_topic = "zigbee2mqtt/bridge/request/devices"
        response_topic = "zigbee2mqtt/bridge/response/devices"

        try:
            await self._mqtt_client.subscribe(response_topic)
            await self._mqtt_client.publish(request_topic, b"")

            # Wait up to 5 seconds for the response
            try:
                async with asyncio.timeout(5):
                    async for message in self._mqtt_client.messages:
                        if str(message.topic) == response_topic:
                            payload = json.loads(message.payload.decode())
                            devices = payload.get("data", [])
                            break
            except asyncio.TimeoutError:
                logger.warning("Zigbee2MQTT device list request timed out")
        except Exception:
            logger.exception("Failed to query Zigbee2MQTT devices")

        return devices

    async def _uhubctl_power(self, action: str) -> None:
        """Control USB hub port power via uhubctl."""
        cmd = ["uhubctl", "-a", action]
        if self._usb_port is not None:
            cmd.extend(["-p", str(self._usb_port)])
        if self._usb_hub is not None:
            cmd.extend(["-l", str(self._usb_hub)])

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
            logger.info("uhubctl USB power %s", action)

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
