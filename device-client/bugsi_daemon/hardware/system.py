from bugsi_daemon.hardware.base import HardwareSensor


class SystemMonitor(HardwareSensor):
    """CPU temperature and uptime from sysfs."""

    async def initialize(self) -> None:
        raise NotImplementedError("Real hardware driver not yet implemented")

    async def read(self) -> dict:
        raise NotImplementedError("Real hardware driver not yet implemented")

    async def shutdown(self) -> None:
        raise NotImplementedError("Real hardware driver not yet implemented")

    def is_healthy(self) -> bool:
        raise NotImplementedError("Real hardware driver not yet implemented")
