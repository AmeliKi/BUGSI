import json
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio

from bugsi_daemon.buffer.store import BufferStore
from bugsi_daemon.config import ConfigManager
from bugsi_daemon.hardware_mock.battery import MockBattery
from bugsi_daemon.hardware_mock.solar import MockSolar
from bugsi_daemon.hardware_mock.climate import MockClimate
from bugsi_daemon.hardware_mock.lte import MockLteModem
from bugsi_daemon.hardware_mock.storage import MockStorage
from bugsi_daemon.hardware_mock.system import MockSystem
from bugsi_daemon.hardware_mock.power_mgmt import MockPowerManagement
from bugsi_daemon.hardware_mock.event_camera import MockEventCamera
from bugsi_daemon.hardware_mock.wlan import MockWlan


@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path


@pytest.fixture
def mock_hardware():
    """Return a dict of all mock hardware instances."""
    return {
        "battery": MockBattery(),
        "solar": MockSolar(),
        "climate": MockClimate(),
        "lte": MockLteModem(),
        "storage": MockStorage(),
        "system": MockSystem(),
        "power_mgmt": MockPowerManagement(),
        "event_camera": MockEventCamera(),
        "wlan": MockWlan(),
    }


@pytest_asyncio.fixture
async def buffer_store(tmp_path):
    """SQLite buffer store using a temp file."""
    db_path = str(tmp_path / "test_buffer.db")
    store = BufferStore(db_path)
    await store.initialize()
    yield store
    await store.close()


@pytest.fixture
def config_manager(tmp_path, monkeypatch):
    """ConfigManager with temp paths and test credentials."""
    # Clear env vars so they don't override test credentials
    monkeypatch.delenv("BUGSI_API_KEY", raising=False)
    monkeypatch.delenv("BUGSI_API_URL", raising=False)
    default_config = {
        "still_camera": {
            "type": "mock",
            "resolution_width": 640,
            "resolution_height": 480,
            "camera_id": 1,
            "autofocus_mode": "continuous",
            "jpeg_quality": 85,
            "exposure_us": 0,
            "gain_db": 0.0,
            "white_balance": "auto",
            "balance_ratio_red": 1.0,
            "balance_ratio_green": 1.0,
            "balance_ratio_blue": 1.0,
            "gamma": 1.0,
            "black_level": 0.0,
            "acquisition_frame_rate": 0.0,
            "binning_horizontal": 1,
            "binning_vertical": 1,
        },
        "event_camera": {
            "type": "mock",
            "device_path": "/dev/video0",
            "event_threshold": 500,
            "detection_window_ms": 50,
            "min_cluster_area": 100,
            "jpeg_quality": 85,
            "bias_diff_on": 102,
            "bias_diff_off": 73,
            "bias_fo": 1450,
            "bias_hpf": 1500,
            "bias_refr": 1500,
        },
        "image_capture": {
            "enabled": True,
            "cooldown_seconds": 0,
            "zigbee_warmup_seconds": 0,
            "save_dir": str(tmp_path / "detections"),
            "thumbnail_width": 160,
            "thumbnail_height": 120,
            "save_full_resolution": True,
        },
        "telemetry": {"collection_interval_minutes": 5},
        "upload": {
            "interval_minutes": 60,
            "max_batch_size": 100,
            "battery_soc_threshold": 20,
            "ota_check_enabled": True,
        },
        "power": {
            "night_mode_enabled": True,
            "night_mode_type": "fixed",
            "awake_start_hour": 7,
            "awake_end_hour": 21,
            "modem_always_off": True,
            "battery": False,
            "wlan_timeout_minutes": 10,
            "energy_saving": False,
            "energy_saving_wlan_minutes": 10,
        },
        "zigbee": {
            "serial_port": "auto",
            "adapter": "ezsp",
            "device_name": "SNZB-02WD",
            "database_path": str(tmp_path / "zigbee.db"),
            "network_channel": 11,
        },
        "storage": {
            "buffer_db_path": str(tmp_path / "buffer.db"),
            "backup_path": str(tmp_path / "backup"),
            "backup_interval_minutes": 60,
            "cleanup_after_days": 30,
        },
    }
    default_path = tmp_path / "default.json"
    default_path.write_text(json.dumps(default_config))

    creds = {"api_key": "bugsi_test_key_123", "api_url": "http://test:8000/api/device-data"}
    creds_path = tmp_path / "credentials.json"
    creds_path.write_text(json.dumps(creds))

    config = ConfigManager(
        default_config_path=default_path,
        local_config_path=tmp_path / "local_config.json",
        credentials_path=creds_path,
    )
    config.load()
    return config
