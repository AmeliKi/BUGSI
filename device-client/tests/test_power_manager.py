import pytest

from bugsi_daemon.buffer.backup import BufferBackup
from bugsi_daemon.core.power_manager import PowerManager, PowerMode


@pytest.mark.asyncio
class TestPowerManager:
    def _make_pm(self, config_manager, mock_hardware, tmp_path):
        backup = BufferBackup(str(tmp_path / "buffer.db"), str(tmp_path / "backup"))
        return PowerManager(
            config=config_manager,
            lte=mock_hardware["lte"],
            power_mgmt=mock_hardware["power_mgmt"],
            backup=backup,
        )

    async def test_initial_mode_is_active(self, config_manager, mock_hardware, tmp_path):
        pm = self._make_pm(config_manager, mock_hardware, tmp_path)
        assert pm.mode == PowerMode.ACTIVE

    async def test_set_mode_upload_powers_on_lte(self, config_manager, mock_hardware, tmp_path):
        pm = self._make_pm(config_manager, mock_hardware, tmp_path)
        await mock_hardware["lte"].power_off()

        await pm.set_mode(PowerMode.UPLOAD)
        assert pm.mode == PowerMode.UPLOAD
        assert mock_hardware["lte"].is_powered()

    async def test_set_mode_active_from_upload_powers_off_lte(self, config_manager, mock_hardware, tmp_path):
        pm = self._make_pm(config_manager, mock_hardware, tmp_path)

        await pm.set_mode(PowerMode.UPLOAD)
        assert mock_hardware["lte"].is_powered()

        await pm.set_mode(PowerMode.ACTIVE)
        assert not mock_hardware["lte"].is_powered()

    async def test_set_mode_low_battery_powers_off_lte(self, config_manager, mock_hardware, tmp_path):
        pm = self._make_pm(config_manager, mock_hardware, tmp_path)

        await pm.set_mode(PowerMode.UPLOAD)
        assert mock_hardware["lte"].is_powered()

        await pm.set_mode(PowerMode.LOW_BATTERY)
        assert not mock_hardware["lte"].is_powered()

    def test_check_night_mode(self, config_manager, mock_hardware, tmp_path):
        pm = self._make_pm(config_manager, mock_hardware, tmp_path)

        # Default: night_start=22, night_end=6
        assert pm.check_night_mode(23) is True
        assert pm.check_night_mode(3) is True
        assert pm.check_night_mode(12) is False
        assert pm.check_night_mode(22) is True
        assert pm.check_night_mode(6) is False

    def test_check_low_battery(self, config_manager, mock_hardware, tmp_path):
        pm = self._make_pm(config_manager, mock_hardware, tmp_path)

        # Default threshold: 20
        assert pm.check_low_battery(15.0) is True
        assert pm.check_low_battery(25.0) is False
        assert pm.check_low_battery(20.0) is False

    async def test_prepare_shutdown(self, config_manager, mock_hardware, tmp_path):
        pm = self._make_pm(config_manager, mock_hardware, tmp_path)
        await mock_hardware["power_mgmt"].initialize()

        await pm.set_mode(PowerMode.UPLOAD)
        await pm.prepare_shutdown()

        assert pm.mode == PowerMode.NIGHT
        assert not mock_hardware["lte"].is_powered()
        wakeup = await mock_hardware["power_mgmt"].get_next_wakeup()
        assert wakeup is not None
