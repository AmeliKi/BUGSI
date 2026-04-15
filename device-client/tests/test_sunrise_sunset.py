"""Tests for sunrise/sunset power management."""
from __future__ import annotations

import json

import pytest
import pytest_asyncio

from bugsi_daemon.buffer.backup import BufferBackup
from bugsi_daemon.config import ConfigManager
from bugsi_daemon.core.power_manager import PowerManager
from bugsi_daemon.hardware_mock.lte import MockLteModem
from bugsi_daemon.hardware_mock.power_mgmt import MockPowerManagement


@pytest.fixture
def power_manager_with_config(tmp_path, monkeypatch):
    """Create a PowerManager with configurable settings."""
    monkeypatch.delenv("BUGSI_API_KEY", raising=False)
    monkeypatch.delenv("BUGSI_API_URL", raising=False)

    def _make(power_config: dict):
        config_data = {
            "power": power_config,
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

        lte = MockLteModem()
        power_mgmt = MockPowerManagement()
        backup = BufferBackup(str(tmp_path / "buffer.db"), str(tmp_path / "backup"))

        return PowerManager(
            config=config,
            lte=lte,
            power_mgmt=power_mgmt,
            backup=backup,
        )

    return _make


class TestFixedMode:
    def test_returns_config_hours(self, power_manager_with_config):
        pm = power_manager_with_config({
            "night_mode_enabled": True,
            "night_mode_type": "fixed",
            "awake_start_hour": 7,
            "awake_end_hour": 21,
        })
        assert pm.get_active_hours() == (7, 21)

    def test_custom_hours(self, power_manager_with_config):
        pm = power_manager_with_config({
            "night_mode_enabled": True,
            "night_mode_type": "fixed",
            "awake_start_hour": 5,
            "awake_end_hour": 23,
        })
        assert pm.get_active_hours() == (5, 23)

    def test_night_mode_during_night(self, power_manager_with_config):
        pm = power_manager_with_config({
            "night_mode_enabled": True,
            "night_mode_type": "fixed",
            "awake_start_hour": 7,
            "awake_end_hour": 21,
        })
        assert pm.check_night_mode(3) is True  # 3 AM → night
        assert pm.check_night_mode(22) is True  # 10 PM → night

    def test_night_mode_during_day(self, power_manager_with_config):
        pm = power_manager_with_config({
            "night_mode_enabled": True,
            "night_mode_type": "fixed",
            "awake_start_hour": 7,
            "awake_end_hour": 21,
        })
        assert pm.check_night_mode(7) is False  # 7 AM → awake
        assert pm.check_night_mode(12) is False  # noon → awake
        assert pm.check_night_mode(20) is False  # 8 PM → awake

    def test_night_mode_disabled(self, power_manager_with_config):
        pm = power_manager_with_config({
            "night_mode_enabled": False,
            "night_mode_type": "fixed",
            "awake_start_hour": 7,
            "awake_end_hour": 21,
        })
        assert pm.check_night_mode(3) is False  # disabled → never night

    def test_default_hours(self, power_manager_with_config):
        pm = power_manager_with_config({
            "night_mode_enabled": True,
            "night_mode_type": "fixed",
        })
        assert pm.get_active_hours() == (7, 21)


class TestSunriseSunsetMode:
    def test_calculates_hours_from_location(self, power_manager_with_config):
        pm = power_manager_with_config({
            "night_mode_enabled": True,
            "night_mode_type": "sunrise_sunset",
            "location_lat": 48.2082,  # Vienna
            "location_lon": 16.3738,
        })
        start, end = pm.get_active_hours()
        # Sunrise is between 4-8, sunset between 16-21 depending on season
        assert 3 <= start <= 9
        assert 15 <= end <= 22

    def test_with_offset(self, power_manager_with_config):
        pm_no_offset = power_manager_with_config({
            "night_mode_enabled": True,
            "night_mode_type": "sunrise_sunset",
            "location_lat": 48.2082,
            "location_lon": 16.3738,
            "sunrise_offset_minutes": 0,
            "sunset_offset_minutes": 0,
        })
        pm_with_offset = power_manager_with_config({
            "night_mode_enabled": True,
            "night_mode_type": "sunrise_sunset",
            "location_lat": 48.2082,
            "location_lon": 16.3738,
            "sunrise_offset_minutes": 60,
            "sunset_offset_minutes": -60,
        })
        start_no, end_no = pm_no_offset.get_active_hours()
        start_off, end_off = pm_with_offset.get_active_hours()
        # With +60min sunrise offset, start should be later
        assert start_off >= start_no
        # With -60min sunset offset, end should be earlier
        assert end_off <= end_no

    def test_fallback_when_no_location(self, power_manager_with_config):
        pm = power_manager_with_config({
            "night_mode_enabled": True,
            "night_mode_type": "sunrise_sunset",
            "location_lat": None,
            "location_lon": None,
            "awake_start_hour": 7,
            "awake_end_hour": 21,
        })
        # Should fall back to fixed mode
        assert pm.get_active_hours() == (7, 21)
