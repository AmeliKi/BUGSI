import json

import pytest

from bugsi_daemon.config import ConfigManager, _deep_merge


class TestDeepMerge:
    def test_simple_merge(self):
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = _deep_merge(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge(self):
        base = {"a": {"x": 1, "y": 2}}
        override = {"a": {"y": 3, "z": 4}}
        result = _deep_merge(base, override)
        assert result == {"a": {"x": 1, "y": 3, "z": 4}}

    def test_does_not_mutate_base(self):
        base = {"a": 1}
        override = {"b": 2}
        _deep_merge(base, override)
        assert base == {"a": 1}


class TestConfigManager:
    def test_load_defaults(self, config_manager):
        assert config_manager.get("telemetry.collection_interval_minutes") == 5
        assert config_manager.get("upload.interval_minutes") == 60

    def test_get_dotted_key(self, config_manager):
        assert config_manager.get("upload.battery_soc_threshold") == 20

    def test_get_missing_key_returns_default(self, config_manager):
        assert config_manager.get("nonexistent.key", 42) == 42

    def test_get_all(self, config_manager):
        all_config = config_manager.get_all()
        assert "telemetry" in all_config
        assert "upload" in all_config

    def test_credentials_loaded(self, config_manager):
        assert config_manager.api_key == "bugsi_test_key_123"
        assert config_manager.api_url == "http://test:8000/api/device-data"

    def test_apply_remote(self, config_manager):
        remote = {"upload": {"interval_minutes": 30}}
        changed = config_manager.apply_remote(remote, version=1)
        assert changed
        assert config_manager.get("upload.interval_minutes") == 30
        assert config_manager.version == 1

    def test_apply_remote_old_version_ignored(self, config_manager):
        config_manager.apply_remote({"upload": {"interval_minutes": 30}}, version=2)
        changed = config_manager.apply_remote({"upload": {"interval_minutes": 10}}, version=1)
        assert not changed
        assert config_manager.get("upload.interval_minutes") == 30

    def test_apply_remote_persists_locally(self, config_manager, tmp_path):
        config_manager.apply_remote({"upload": {"interval_minutes": 15}}, version=3)

        local_path = tmp_path / "local_config.json"
        assert local_path.exists()
        data = json.loads(local_path.read_text())
        assert data["version"] == 3
        assert data["config"]["upload"]["interval_minutes"] == 15

    def test_missing_credentials_not_configured(self, tmp_path, monkeypatch):
        monkeypatch.delenv("BUGSI_API_KEY", raising=False)
        monkeypatch.delenv("BUGSI_API_URL", raising=False)
        default_path = tmp_path / "default.json"
        default_path.write_text(json.dumps({}))

        config = ConfigManager(
            default_config_path=default_path,
            local_config_path=tmp_path / "local.json",
            credentials_path=tmp_path / "nonexistent_creds.json",
        )
        config.load()
        assert not config.is_configured

    def test_set_credentials_from_cli(self, tmp_path, monkeypatch):
        monkeypatch.delenv("BUGSI_API_KEY", raising=False)
        monkeypatch.delenv("BUGSI_API_URL", raising=False)
        default_path = tmp_path / "default.json"
        default_path.write_text(json.dumps({}))

        config = ConfigManager(
            default_config_path=default_path,
            local_config_path=tmp_path / "local.json",
            credentials_path=tmp_path / "nonexistent_creds.json",
        )
        config.load()
        assert not config.is_configured
        config.set_credentials(api_key="cli_key", api_url="http://cli:8000/api")
        assert config.is_configured
        assert config.api_key == "cli_key"
        assert config.api_url == "http://cli:8000/api"

    def test_env_var_override(self, tmp_path, monkeypatch):
        default_path = tmp_path / "default.json"
        default_path.write_text(json.dumps({}))

        monkeypatch.setenv("BUGSI_API_KEY", "env_key")
        monkeypatch.setenv("BUGSI_API_URL", "http://env:9000/api")

        config = ConfigManager(
            default_config_path=default_path,
            local_config_path=tmp_path / "local.json",
            credentials_path=tmp_path / "nonexistent.json",
        )
        config.load()
        assert config.api_key == "env_key"
        assert config.api_url == "http://env:9000/api"
