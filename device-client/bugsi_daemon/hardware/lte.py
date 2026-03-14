from bugsi_daemon.hardware.base import LteModemInterface


class SixfabLteModem(LteModemInterface):
    """Sixfab EG25-G LTE modem with GPIO16 hardware power control."""

    async def power_on(self) -> None:
        raise NotImplementedError("Real hardware driver not yet implemented")

    async def power_off(self) -> None:
        raise NotImplementedError("Real hardware driver not yet implemented")

    def is_powered(self) -> bool:
        raise NotImplementedError("Real hardware driver not yet implemented")

    async def wait_for_network(self, timeout: float = 60.0) -> bool:
        raise NotImplementedError("Real hardware driver not yet implemented")

    async def get_signal_info(self) -> dict:
        raise NotImplementedError("Real hardware driver not yet implemented")
