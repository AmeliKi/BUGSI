from bugsi_daemon.hardware.base import PowerManagementInterface


class WittyPiPowerManager(PowerManagementInterface):
    """Witty Pi 4 Mini - RTC and power scheduling via I2C."""

    async def initialize(self) -> None:
        raise NotImplementedError("Real hardware driver not yet implemented")

    async def get_rtc_time(self):
        raise NotImplementedError("Real hardware driver not yet implemented")

    async def set_rtc_time(self, dt):
        raise NotImplementedError("Real hardware driver not yet implemented")

    async def schedule_shutdown(self, at):
        raise NotImplementedError("Real hardware driver not yet implemented")

    async def schedule_wakeup(self, at):
        raise NotImplementedError("Real hardware driver not yet implemented")

    async def get_next_wakeup(self):
        raise NotImplementedError("Real hardware driver not yet implemented")

    async def get_wakeup_reason(self) -> str:
        raise NotImplementedError("Real hardware driver not yet implemented")

    async def shutdown(self) -> None:
        raise NotImplementedError("Real hardware driver not yet implemented")
