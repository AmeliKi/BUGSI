import pytest

from bugsi_daemon.hardware.base import HardwareSensor, PowerControllable
from bugsi_daemon.hardware_mock.climate import MockClimate


@pytest.mark.asyncio
class TestMockClimatePower:
    async def test_implements_interfaces(self):
        climate = MockClimate()
        assert isinstance(climate, HardwareSensor)
        assert isinstance(climate, PowerControllable)

    async def test_starts_powered_off(self):
        climate = MockClimate()
        assert not climate.is_powered()
        assert not climate.is_healthy()

    async def test_power_on_off(self):
        climate = MockClimate()
        await climate.power_on()
        assert climate.is_powered()
        assert climate.is_healthy()
        await climate.power_off()
        assert not climate.is_powered()
        assert not climate.is_healthy()

    async def test_read_when_powered(self):
        climate = MockClimate()
        await climate.power_on()
        reading = await climate.read()
        assert "temperature" in reading
        assert "humidity" in reading
        assert 5.0 <= reading["temperature"] <= 35.0
        assert 30.0 <= reading["humidity"] <= 90.0

    async def test_read_when_powered_off_returns_last_known(self):
        climate = MockClimate()
        await climate.power_on()
        reading1 = await climate.read()
        await climate.power_off()
        reading2 = await climate.read()
        # Should return the last known values
        assert reading2 == reading1

    async def test_read_when_never_powered_returns_empty(self):
        climate = MockClimate()
        reading = await climate.read()
        assert reading == {}

    async def test_initialize_powers_on(self):
        climate = MockClimate()
        await climate.initialize()
        assert climate.is_powered()
        assert climate.is_healthy()

    async def test_read_returns_extended_fields(self):
        climate = MockClimate()
        await climate.power_on()
        reading = await climate.read()
        assert "sensor_battery" in reading
        assert 0 <= reading["sensor_battery"] <= 100
        assert "sensor_voltage" in reading
        assert 2800 <= reading["sensor_voltage"] <= 3200
        assert "zigbee_linkquality" in reading
        assert 0 <= reading["zigbee_linkquality"] <= 255

    async def test_get_devices_returns_generic_name(self):
        climate = MockClimate()
        await climate.power_on()
        devices = await climate.get_devices()
        assert len(devices) == 1
        assert devices[0]["friendly_name"] == "climate_sensor"

    async def test_pair_zigbee(self):
        climate = MockClimate()
        await climate.power_on()
        callback_data = []
        joined = await climate.pair_zigbee(
            timeout=5, on_device_joined=lambda d: callback_data.append(d),
        )
        assert len(joined) == 1
        assert joined[0]["ieee_address"] == "0x00124b00abcdef01"
        assert len(callback_data) == 1

    async def test_rename_device(self):
        climate = MockClimate()
        await climate.power_on()
        result = await climate.rename_device("old", "new")
        assert result is True
