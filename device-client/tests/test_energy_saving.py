"""Tests for energy saving mode."""
from __future__ import annotations

import json

import pytest
import pytest_asyncio

from bugsi_daemon.buffer.backup import BufferBackup
from bugsi_daemon.config import ConfigManager
from bugsi_daemon.core.power_manager import PowerManager
from bugsi_daemon.hardware_mock.lte import MockLteModem
from bugsi_daemon.hardware_mock.power_mgmt import MockPowerManagement
from bugsi_daemon.hardware_mock.wlan import MockWlan


@pytest.fixture
def energy_saving_setup(tmp_path, monkeypatch):
    """Create PowerManager + MockWlan for energy saving tests."""
    monkeypatch.delenv("BUGSI_API_KEY", raising=False)
    monkeypatch.delenv("BUGSI_API_URL", raising=False)

    def _make(energy_saving: bool = True, wlan_minutes: int = 10):
        config_data = {
            "power": {
                "energy_saving": energy_saving,
                "energy_saving_wlan_minutes": wlan_minutes,
            },
            "storage": {
                "buffer_db_path": str(tmp_path / "buffer.db"),
                "backup_path": str(tmp_path / "backup"),
            },
        }
        default_path = tmp_path / "default.json"
        default_path.write_text(json.dumps(config_data))
        creds_path = tmp_path / "credentials.json"
        creds_path.write_text(json.dumps({
            "api_key": "test_key",
            "api_url": "http://test:8000",
        }))
        config = ConfigManager(
            default_config_path=default_path,
            local_config_path=tmp_path / "local_config.json",
            credentials_path=creds_path,
        )
        config.load()

        wlan = MockWlan()
        lte = MockLteModem()
        power_mgmt = MockPowerManagement()
        backup = BufferBackup(str(tmp_path / "buffer.db"), str(tmp_path / "backup"))

        pm = PowerManager(
            config=config,
            lte=lte,
            power_mgmt=power_mgmt,
            backup=backup,
            wlan=wlan,
        )
        return pm, wlan

    return _make


@pytest.mark.asyncio
class TestEnergySaving:
    async def test_disabled_no_effect(self, energy_saving_setup):
        pm, wlan = energy_saving_setup(energy_saving=False)
        assert wlan.is_enabled()
        await pm.apply_energy_saving("rtc_wake")
        assert wlan.is_enabled()  # No change

    async def test_rtc_wake_disables_wlan(self, energy_saving_setup):
        pm, wlan = energy_saving_setup(energy_saving=True)
        assert wlan.is_enabled()
        await pm.apply_energy_saving("rtc_wake")
        assert not wlan.is_enabled()

    async def test_cold_boot_keeps_wlan(self, energy_saving_setup):
        pm, wlan = energy_saving_setup(energy_saving=True)
        assert wlan.is_enabled()
        await pm.apply_energy_saving("cold_boot")
        assert wlan.is_enabled()  # Cold boot keeps WLAN on
