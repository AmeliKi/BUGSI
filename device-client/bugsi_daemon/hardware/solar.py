from bugsi_daemon.hardware.base import HardwareSensor


class VictronSmartSolar(HardwareSensor):
    """Victron SmartSolar MPPT 100/20 via VE.Direct USB serial."""

    async def initialize(self) -> None:
        raise NotImplementedError("Real hardware driver not yet implemented")

    async def read(self) -> dict:
        raise NotImplementedError("Real hardware driver not yet implemented")

    async def shutdown(self) -> None:
        raise NotImplementedError("Real hardware driver not yet implemented")

    def is_healthy(self) -> bool:
        raise NotImplementedError("Real hardware driver not yet implemented")
