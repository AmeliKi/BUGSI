import pytest

from bugsi_daemon.hardware_mock.lte import MockLteModem


@pytest.mark.asyncio
class TestMockLteModem:
    async def test_starts_powered_off(self):
        modem = MockLteModem()
        assert not modem.is_powered()

    async def test_power_on_off(self):
        modem = MockLteModem()
        await modem.power_on()
        assert modem.is_powered()
        await modem.power_off()
        assert not modem.is_powered()

    async def test_wait_for_network_when_powered(self):
        modem = MockLteModem()
        await modem.power_on()
        result = await modem.wait_for_network(timeout=5.0)
        assert result is True

    async def test_wait_for_network_when_off(self):
        modem = MockLteModem()
        result = await modem.wait_for_network(timeout=5.0)
        assert result is False

    async def test_signal_info_when_powered(self):
        modem = MockLteModem()
        await modem.power_on()
        info = await modem.get_signal_info()

        assert "lte_signal_strength" in info
        assert "lte_signal_quality" in info
        assert -110 <= info["lte_signal_strength"] <= -60
        assert -20 <= info["lte_signal_quality"] <= -3

    async def test_signal_info_when_off(self):
        modem = MockLteModem()
        info = await modem.get_signal_info()

        assert info["lte_signal_strength"] is None
        assert info["lte_signal_quality"] is None
