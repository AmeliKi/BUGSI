"""Sixfab/Quectel EG25-G LTE modem driver.

Uses gpiod for PIN 26 hardware power control and AT commands via serial.
Only works on Raspberry Pi with the modem connected.
"""
from __future__ import annotations

import asyncio
import glob
import logging
import os

from bugsi_daemon.hardware.base import LteModemInterface

logger = logging.getLogger(__name__)

MODEM_GPIO_PIN = 26
MODEM_SERIAL_PORT = "/dev/ttyUSB2"
MODEM_BAUD_RATE = 115200
MODEM_BOOT_TIMEOUT = 30.0
MODEM_PORT_RETRY_INTERVAL = 2.0
MODEM_PORT_RETRY_TIMEOUT = 60.0

# Quectel EG25-G USB vendor:product ID
QUECTEL_VID_PID = "2c7c:0125"


def _find_modem_port() -> str | None:
    """Auto-detect the Quectel AT command serial port.

    The EG25-G exposes multiple ttyUSB ports. The AT command port is
    typically the third one (index 2), but numbering depends on other
    USB devices. We find it by matching the USB vendor:product ID via
    sysfs, then picking the port whose interface number is 02 (AT commands).
    Falls back to checking all /dev/ttyUSB* ports.
    """
    # Strategy 1: Match via sysfs USB device tree
    for tty_path in sorted(glob.glob("/sys/class/tty/ttyUSB*")):
        device_link = os.path.join(tty_path, "device")
        if not os.path.islink(device_link):
            continue
        real_path = os.path.realpath(device_link)

        # Walk up to find the USB device with idVendor/idProduct
        usb_dir = real_path
        for _ in range(10):
            vid_path = os.path.join(usb_dir, "idVendor")
            pid_path = os.path.join(usb_dir, "idProduct")
            if os.path.exists(vid_path) and os.path.exists(pid_path):
                vid = open(vid_path).read().strip()
                pid = open(pid_path).read().strip()
                if f"{vid}:{pid}" == QUECTEL_VID_PID:
                    # Check interface number — AT port is bInterfaceNumber 02
                    intf_path = os.path.join(
                        os.path.dirname(real_path), "bInterfaceNumber"
                    )
                    if os.path.exists(intf_path):
                        intf_num = open(intf_path).read().strip()
                        if intf_num == "02":
                            port_name = os.path.basename(tty_path)
                            return f"/dev/{port_name}"
                break
            usb_dir = os.path.dirname(usb_dir)

    # Strategy 2: Try each /dev/ttyUSB* and see which responds to AT
    for dev in sorted(glob.glob("/dev/ttyUSB*")):
        try:
            import serial
            with serial.Serial(dev, MODEM_BAUD_RATE, timeout=1) as ser:
                ser.write(b"AT\r\n")
                resp = ser.read(64).decode(errors="replace")
                if "OK" in resp:
                    return dev
        except Exception:
            continue

    return None


class SixfabLteModem(LteModemInterface):
    """Sixfab EG25-G LTE modem with gpiod PIN 26 hardware power control."""

    def __init__(
        self,
        gpio_pin: int = MODEM_GPIO_PIN,
        serial_port: str | None = None,
    ) -> None:
        self._gpio_pin = gpio_pin
        self._serial_port = serial_port  # None = auto-detect
        self._active_port: str | None = None  # resolved port for this session
        self._powered = False
        self._gpio_chip = None
        self._gpio_line = None
        self._serial_conn = None  # persistent serial connection

    async def power_on(self) -> None:
        if self._powered:
            return

        try:
            import gpiod
        except ImportError:
            raise NotImplementedError(
                "gpiod not available — install it on Raspberry Pi"
            )

        # Open GPIO chip and request the power line
        self._gpio_chip = gpiod.Chip("/dev/gpiochip4")
        config = gpiod.LineSettings(
            direction=gpiod.line.Direction.OUTPUT,
            output_value=gpiod.line.Value.INACTIVE,
        )
        self._gpio_line = self._gpio_chip.request_lines(
            consumer="bugsi-lte",
            config={self._gpio_pin: config},
        )

        # Pull LOW to power on modem
        self._gpio_line.set_value(self._gpio_pin, gpiod.line.Value.ACTIVE)
        logger.info("LTE modem power on (GPIO %d LOW)", self._gpio_pin)

        # Wait for serial port to appear, retrying until timeout
        self._active_port = await self._wait_for_serial_port()
        if self._active_port is None:
            logger.error(
                "LTE modem serial port not found after %.0fs",
                MODEM_PORT_RETRY_TIMEOUT,
            )
            return

        # Open persistent serial connection
        import serial
        self._serial_conn = serial.Serial(
            self._active_port, MODEM_BAUD_RATE, timeout=2
        )

        # Verify modem responds to AT (retry a few times — port may appear
        # before the modem firmware is fully ready)
        for attempt in range(5):
            try:
                response = await self._send_at_command("AT", timeout=5.0)
                if "OK" in response:
                    self._powered = True
                    logger.info(
                        "LTE modem booted on %s", self._active_port
                    )
                    return
            except Exception:
                if attempt < 4:
                    logger.debug(
                        "AT probe attempt %d failed, retrying...", attempt + 1
                    )
                    await asyncio.sleep(MODEM_PORT_RETRY_INTERVAL)

        logger.error("LTE modem did not respond to AT command on %s", self._active_port)

    async def _wait_for_serial_port(self) -> str | None:
        """Wait for the modem serial port to appear after GPIO power-on."""
        loop = asyncio.get_event_loop()
        deadline = loop.time() + MODEM_PORT_RETRY_TIMEOUT

        while loop.time() < deadline:
            # If a specific port was configured, just wait for it to exist
            if self._serial_port:
                if os.path.exists(self._serial_port):
                    logger.info("Serial port found: %s", self._serial_port)
                    return self._serial_port
            else:
                # Auto-detect
                port = await loop.run_in_executor(None, _find_modem_port)
                if port:
                    logger.info("Auto-detected modem port: %s", port)
                    return port

            logger.debug(
                "Waiting for modem serial port (%.0fs remaining)...",
                deadline - loop.time(),
            )
            await asyncio.sleep(MODEM_PORT_RETRY_INTERVAL)

        return None

    async def power_off(self) -> None:
        if not self._powered:
            return

        # Graceful shutdown via AT command
        try:
            await self._send_at_command("AT+QPOWD", timeout=5.0)
            await asyncio.sleep(2.0)
        except Exception:
            logger.warning("AT+QPOWD failed, forcing hardware power off")

        # Close persistent serial connection
        if self._serial_conn is not None:
            try:
                self._serial_conn.close()
            except Exception:
                pass
            self._serial_conn = None

        # Hardware power cutoff via GPIO
        if self._gpio_line is not None:
            import gpiod
            self._gpio_line.set_value(self._gpio_pin, gpiod.line.Value.INACTIVE)
            self._gpio_line.release()
            self._gpio_line = None
        if self._gpio_chip is not None:
            self._gpio_chip.close()
            self._gpio_chip = None

        self._powered = False
        self._active_port = None
        logger.info("LTE modem powered off (GPIO %d HIGH)", self._gpio_pin)

    def is_powered(self) -> bool:
        return self._powered

    async def wait_for_network(self, timeout: float = 60.0) -> bool:
        if not self._powered:
            return False

        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            try:
                response = await self._send_at_command("AT+CREG?", timeout=5.0)
                # +CREG: 0,1 = registered home, +CREG: 0,5 = registered roaming
                if "+CREG:" in response:
                    parts = response.split(",")
                    if len(parts) >= 2:
                        status = parts[1].strip().rstrip("\r\nOK ")
                        if status in ("1", "5"):
                            logger.info("LTE network registered (status=%s)", status)
                            return True
            except Exception:
                logger.debug("Network check failed, retrying...")

            await asyncio.sleep(2.0)

        logger.error("LTE network registration timeout after %.0fs", timeout)
        return False

    async def get_signal_info(self) -> dict:
        if not self._powered:
            return {"lte_signal_strength": None, "lte_signal_quality": None}

        result = {"lte_signal_strength": None, "lte_signal_quality": None}

        try:
            # AT+CSQ returns signal strength (0-31, 99=unknown)
            response = await self._send_at_command("AT+CSQ", timeout=5.0)
            if "+CSQ:" in response:
                parts = response.split(":")[1].strip().split(",")
                rssi_raw = int(parts[0])
                if rssi_raw != 99:
                    # Convert to dBm: -113 + 2*rssi
                    result["lte_signal_strength"] = -113 + 2 * rssi_raw

            # AT+QCSQ for detailed LTE signal quality
            response = await self._send_at_command("AT+QCSQ", timeout=5.0)
            if "+QCSQ:" in response and "LTE" in response:
                parts = response.split(",")
                if len(parts) >= 3:
                    rsrq = int(parts[2].strip())
                    result["lte_signal_quality"] = rsrq

        except Exception:
            logger.exception("Failed to read LTE signal info")

        return result

    async def _send_at_command(self, command: str, timeout: float = 5.0) -> str:
        """Send an AT command and return the response."""
        loop = asyncio.get_event_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(None, self._send_at_sync, command),
            timeout=timeout,
        )

    def _send_at_sync(self, command: str) -> str:
        """Synchronous AT command via persistent serial connection."""
        ser = self._serial_conn
        if ser is None or not ser.is_open:
            import serial
            port = self._active_port or self._serial_port or MODEM_SERIAL_PORT
            self._serial_conn = serial.Serial(port, MODEM_BAUD_RATE, timeout=2)
            ser = self._serial_conn

        ser.reset_input_buffer()
        ser.write(f"{command}\r\n".encode())
        response = ""
        while True:
            line = ser.readline().decode(errors="replace")
            if not line:
                break
            response += line
            if "OK" in line or "ERROR" in line:
                break
        return response
