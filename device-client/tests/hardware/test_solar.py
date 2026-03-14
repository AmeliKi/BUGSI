import pytest

from bugsi_daemon.hardware_mock.solar import MockSolar


@pytest.mark.asyncio
class TestMockSolar:
    async def test_initialize(self):
        solar = MockSolar()
        await solar.initialize()
        assert solar.is_healthy()

    async def test_read_returns_all_fields(self):
        solar = MockSolar()
        await solar.initialize()
        data = await solar.read()

        assert "solar_pv_voltage" in data
        assert "solar_pv_power" in data
        assert "solar_charge_current" in data

    async def test_values_non_negative(self):
        solar = MockSolar()
        await solar.initialize()
        data = await solar.read()

        assert data["solar_pv_voltage"] >= 0
        assert data["solar_pv_power"] >= 0
        assert data["solar_charge_current"] >= 0

    async def test_shutdown(self):
        solar = MockSolar()
        await solar.initialize()
        await solar.shutdown()
        assert not solar.is_healthy()
