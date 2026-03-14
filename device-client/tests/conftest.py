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
        "telemetry": {"collection_interval_minutes": 5},
        "upload": {"interval_minutes": 60, "max_batch_size": 100, "battery_soc_threshold": 20},
        "power": {"night_mode_enabled": True, "night_start_hour": 22, "night_end_hour": 6},
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
