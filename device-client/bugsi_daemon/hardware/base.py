from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime


class HardwareSensor(ABC):
    """Base class for all hardware sensors."""

    @abstractmethod
    async def initialize(self) -> None:
        """Set up the sensor (open ports, configure, etc.)."""

    @abstractmethod
    async def read(self) -> dict:
        """Read current sensor values. Returns a dict of field_name -> value."""

    @abstractmethod
    async def shutdown(self) -> None:
        """Gracefully release resources."""

    @abstractmethod
    def is_healthy(self) -> bool:
        """Return True if the sensor is operational."""


class PowerControllable(ABC):
    """Hardware that can be powered on/off for power saving."""

    @abstractmethod
    async def power_on(self) -> None:
        """Power on the hardware."""

    @abstractmethod
    async def power_off(self) -> None:
        """Power off the hardware (should draw 0 mA if possible)."""

    @abstractmethod
    def is_powered(self) -> bool:
        """Return True if the hardware is currently powered on."""


class LteModemInterface(PowerControllable, ABC):
    """LTE modem with hardware power control."""

    @abstractmethod
    async def wait_for_network(self, timeout: float = 60.0) -> bool:
        """Wait for network registration. Returns True if connected."""

    @abstractmethod
    async def get_signal_info(self) -> dict:
        """Return {'lte_signal_strength': int, 'lte_signal_quality': int}."""


class PowerManagementInterface(ABC):
    """Witty Pi 5 - RTC and power scheduling."""

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize communication with power management hardware."""

    @abstractmethod
    async def get_rtc_time(self) -> datetime:
        """Read current time from the RTC."""

    @abstractmethod
    async def set_rtc_time(self, dt: datetime) -> None:
        """Set the RTC time."""

    @abstractmethod
    async def schedule_shutdown(self, at: datetime) -> None:
        """Schedule a system shutdown at the given time."""

    @abstractmethod
    async def schedule_wakeup(self, at: datetime) -> None:
        """Schedule a system wakeup at the given time."""

    @abstractmethod
    async def get_next_wakeup(self) -> datetime | None:
        """Return the next scheduled wakeup time, or None."""

    @abstractmethod
    async def get_wakeup_reason(self) -> str:
        """Return the reason for the last boot: 'rtc_wake' or 'cold_boot'."""

    @abstractmethod
    async def get_temperature(self) -> float:
        """Read temperature from onboard sensor."""

    @abstractmethod
    async def get_input_voltage(self) -> float:
        """Read input voltage."""

    @abstractmethod
    async def shutdown(self) -> None:
        """Release resources."""


class WlanInterface(ABC):
    """Interface for WLAN radio control (power saving)."""

    @abstractmethod
    async def enable(self) -> None:
        """Enable the WLAN radio."""

    @abstractmethod
    async def disable(self) -> None:
        """Disable the WLAN radio to save power."""

    @abstractmethod
    def is_enabled(self) -> bool:
        """Return True if the WLAN radio is currently enabled."""


# --- Camera interfaces ---

class StillCameraInterface(ABC):
    """Interface for still/frame cameras (e.g. Arducam 64MP)."""

    @abstractmethod
    def open(self) -> None:
        """Open the camera and prepare for capture."""

    @abstractmethod
    def close(self) -> None:
        """Release camera resources."""

    @abstractmethod
    def capture(self) -> "np.ndarray":
        """Capture a single frame. Returns a BGR numpy array."""

    @abstractmethod
    def is_open(self) -> bool:
        """Return True if the camera is currently open and ready."""


# Backwards compatibility alias
CameraInterface = StillCameraInterface


class EventCameraInterface(PowerControllable, ABC):
    """Interface for event-based cameras (e.g. Prophesee GenX320)."""

    @abstractmethod
    async def initialize(self) -> None:
        """Open device and configure event processing pipeline."""

    @abstractmethod
    async def start_detection(self) -> None:
        """Start the event stream and begin monitoring for events."""

    @abstractmethod
    async def stop_detection(self) -> None:
        """Stop the event stream."""

    @abstractmethod
    async def wait_for_detection(self, timeout: float | None = None) -> bool:
        """Block until a detection event occurs or timeout. Returns True if detected."""

    @abstractmethod
    async def capture_event_frame(self) -> "np.ndarray":
        """Capture a visualization of recent events as a BGR numpy array."""

    @abstractmethod
    async def shutdown(self) -> None:
        """Release all resources."""

    @abstractmethod
    def is_detecting(self) -> bool:
        """Return True if currently monitoring for events."""


# --- Camera registries ---

STILL_CAMERA_REGISTRY: dict[str, type[StillCameraInterface]] = {}
EVENT_CAMERA_REGISTRY: dict[str, type[EventCameraInterface]] = {}


def register_still_camera(name: str):
    """Decorator to register a still camera driver by type name."""
    def wrapper(cls):
        STILL_CAMERA_REGISTRY[name] = cls
        return cls
    return wrapper


def register_event_camera(name: str):
    """Decorator to register an event camera driver by type name."""
    def wrapper(cls):
        EVENT_CAMERA_REGISTRY[name] = cls
        return cls
    return wrapper
