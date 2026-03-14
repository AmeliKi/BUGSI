from bugsi_daemon.hardware.base import HardwareSensor


class ZigbeeClimateSensor(HardwareSensor):
    """SONOFF SNZB-02WD Zigbee temp/humidity sensor via ZBDongle-E."""

    async def initialize(self) -> None:
        raise NotImplementedError("Real hardware driver not yet implemented")

    async def read(self) -> dict:
        raise NotImplementedError("Real hardware driver not yet implemented")

    async def shutdown(self) -> None:
        raise NotImplementedError("Real hardware driver not yet implemented")

    def is_healthy(self) -> bool:
        raise NotImplementedError("Real hardware driver not yet implemented")
