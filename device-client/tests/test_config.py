import json
from unittest import mock

import pytest

from bugsi_daemon.config import ConfigManager, _deep_merge, _HARDWARE_CONF_PATH


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


class TestStillCameraConfig:
    def test_exposure_gain_defaults(self, config_manager):
        assert config_manager.get("still_camera.exposure_us") == 0
        assert config_manager.get("still_camera.gain_db") == 0.0

    def test_apply_remote_exposure_gain(self, config_manager):
        remote = {"still_camera": {"exposure_us": 10000, "gain_db": 6.0}}
        config_manager.apply_remote(remote, version=1)
        assert config_manager.get("still_camera.exposure_us") == 10000
        assert config_manager.get("still_camera.gain_db") == 6.0
        # Other fields preserved
        assert config_manager.get("still_camera.jpeg_quality") == 85


class TestStillCameraNewParams:
    def test_white_balance_default(self, config_manager):
        assert config_manager.get("still_camera.white_balance") == "auto"

    def test_gamma_default(self, config_manager):
        assert config_manager.get("still_camera.gamma") == 1.0

    def test_black_level_default(self, config_manager):
        assert config_manager.get("still_camera.black_level") == 0.0

    def test_binning_defaults(self, config_manager):
        assert config_manager.get("still_camera.binning_horizontal") == 1
        assert config_manager.get("still_camera.binning_vertical") == 1

    def test_frame_rate_default(self, config_manager):
        assert config_manager.get("still_camera.acquisition_frame_rate") == 0.0

    def test_apply_remote_new_params(self, config_manager):
        remote = {
            "still_camera": {
                "white_balance": "off",
                "balance_ratio_red": 1.5,
                "gamma": 0.8,
                "binning_horizontal": 2,
                "acquisition_frame_rate": 10.0,
            }
        }
        config_manager.apply_remote(remote, version=1)
        assert config_manager.get("still_camera.white_balance") == "off"
        assert config_manager.get("still_camera.balance_ratio_red") == 1.5
        assert config_manager.get("still_camera.gamma") == 0.8
        assert config_manager.get("still_camera.binning_horizontal") == 2
        assert config_manager.get("still_camera.acquisition_frame_rate") == 10.0
        # Existing fields preserved
        assert config_manager.get("still_camera.exposure_us") == 0

    def test_backward_compat_old_config_without_new_fields(self, tmp_path, monkeypatch):
        """Old local config missing new fields gets defaults merged in."""
        monkeypatch.delenv("BUGSI_API_KEY", raising=False)
        monkeypatch.delenv("BUGSI_API_URL", raising=False)
        default_path = tmp_path / "default.json"
        default_path.write_text(json.dumps({
            "still_camera": {
                "type": "ids_rgb",
                "white_balance": "auto",
                "gamma": 1.0,
                "binning_horizontal": 1,
            },
        }))
        local_path = tmp_path / "local.json"
        local_path.write_text(json.dumps({
            "version": 3,
            "config": {"still_camera": {"exposure_us": 5000}},
        }))
        config = ConfigManager(
            default_config_path=default_path,
            local_config_path=local_path,
            credentials_path=tmp_path / "creds.json",
        )
        config.load()
        assert config.get("still_camera.exposure_us") == 5000
        assert config.get("still_camera.white_balance") == "auto"
        assert config.get("still_camera.gamma") == 1.0


class TestEventCameraConfig:
    def test_bias_fields_accessible(self, config_manager):
        assert config_manager.get("event_camera.bias_diff_on") == 102
        assert config_manager.get("event_camera.bias_diff_off") == 73
        assert config_manager.get("event_camera.bias_fo") == 1450
        assert config_manager.get("event_camera.bias_hpf") == 1500
        assert config_manager.get("event_camera.bias_refr") == 1500

    def test_jpeg_quality_accessible(self, config_manager):
        assert config_manager.get("event_camera.jpeg_quality") == 85

    def test_apply_remote_with_bias_fields(self, config_manager):
        remote = {"event_camera": {"bias_diff_on": 110, "bias_fo": 1600}}
        config_manager.apply_remote(remote, version=1)
        assert config_manager.get("event_camera.bias_diff_on") == 110
        assert config_manager.get("event_camera.bias_fo") == 1600
        # Unchanged fields preserved
        assert config_manager.get("event_camera.bias_diff_off") == 73
        assert config_manager.get("event_camera.event_threshold") == 500

    def test_backward_compat_old_config_without_biases(self, tmp_path, monkeypatch):
        """Old local config missing bias fields gets defaults merged in."""
        monkeypatch.delenv("BUGSI_API_KEY", raising=False)
        monkeypatch.delenv("BUGSI_API_URL", raising=False)

        default_path = tmp_path / "default.json"
        default_path.write_text(json.dumps({
            "event_camera": {
                "type": "prophesee_genx320",
                "event_threshold": 500,
                "bias_diff_on": 102,
                "bias_fo": 1450,
            },
        }))

        # Old local config without bias fields
        local_path = tmp_path / "local.json"
        local_path.write_text(json.dumps({
            "version": 3,
            "config": {"event_camera": {"event_threshold": 600}},
        }))

        config = ConfigManager(
            default_config_path=default_path,
            local_config_path=local_path,
            credentials_path=tmp_path / "creds.json",
        )
        config.load()

        # Local override preserved
        assert config.get("event_camera.event_threshold") == 600
        # Defaults filled in for missing bias fields
        assert config.get("event_camera.bias_diff_on") == 102
        assert config.get("event_camera.bias_fo") == 1450

    def test_apply_local_bias_change(self, config_manager):
        new_version = config_manager.apply_local({"event_camera": {"bias_diff_on": 120}})
        assert new_version == 1
        assert config_manager.get("event_camera.bias_diff_on") == 120
        assert config_manager.has_unpushed_changes


class TestHardwareOverrides:
    def test_option_a_sets_ids_cameras(self, tmp_path, monkeypatch):
        monkeypatch.delenv("BUGSI_API_KEY", raising=False)
        monkeypatch.delenv("BUGSI_API_URL", raising=False)

        default_path = tmp_path / "default.json"
        default_path.write_text(json.dumps({
            "still_camera": {"type": "arducam_64mp", "resolution_width": 3840},
            "event_camera": {"type": "prophesee_genx320", "event_threshold": 500},
        }))

        hw_conf = tmp_path / "hardware.conf"
        hw_conf.write_text("HW_CONFIG=A\nINSTALL_DATE=2026-01-01\n")

        with mock.patch("bugsi_daemon.config._HARDWARE_CONF_PATH", str(hw_conf)):
            config = ConfigManager(
                default_config_path=default_path,
                local_config_path=tmp_path / "local.json",
                credentials_path=tmp_path / "creds.json",
            )
            config.load()

        assert config.get("still_camera.type") == "ids_rgb"
        assert config.get("event_camera.type") == "ids_evs"
        # Other fields should be preserved
        assert config.get("still_camera.resolution_width") == 3840
        assert config.get("event_camera.event_threshold") == 500

    def test_option_b_keeps_arducam_with_resolution(self, tmp_path, monkeypatch):
        monkeypatch.delenv("BUGSI_API_KEY", raising=False)
        monkeypatch.delenv("BUGSI_API_URL", raising=False)

        default_path = tmp_path / "default.json"
        default_path.write_text(json.dumps({
            "still_camera": {"type": "arducam_64mp", "resolution_width": 5136, "resolution_height": 3856},
            "event_camera": {"type": "prophesee_genx320"},
        }))

        hw_conf = tmp_path / "hardware.conf"
        hw_conf.write_text("HW_CONFIG=B\n")

        with mock.patch("bugsi_daemon.config._HARDWARE_CONF_PATH", str(hw_conf)):
            config = ConfigManager(
                default_config_path=default_path,
                local_config_path=tmp_path / "local.json",
                credentials_path=tmp_path / "creds.json",
            )
            config.load()

        assert config.get("still_camera.type") == "arducam_64mp"
        assert config.get("still_camera.resolution_width") == 3840
        assert config.get("still_camera.resolution_height") == 2160
        assert config.get("event_camera.type") == "prophesee_genx320"

    def test_no_hardware_conf_uses_defaults(self, tmp_path, monkeypatch):
        monkeypatch.delenv("BUGSI_API_KEY", raising=False)
        monkeypatch.delenv("BUGSI_API_URL", raising=False)

        default_path = tmp_path / "default.json"
        default_path.write_text(json.dumps({
            "still_camera": {"type": "arducam_64mp"},
        }))

        with mock.patch("bugsi_daemon.config._HARDWARE_CONF_PATH", str(tmp_path / "nonexistent")):
            config = ConfigManager(
                default_config_path=default_path,
                local_config_path=tmp_path / "local.json",
                credentials_path=tmp_path / "creds.json",
            )
            config.load()

        assert config.get("still_camera.type") == "arducam_64mp"

    def test_local_config_can_override_hardware(self, tmp_path, monkeypatch):
        """Local config (from user/SaaS) takes priority over hardware.conf."""
        monkeypatch.delenv("BUGSI_API_KEY", raising=False)
        monkeypatch.delenv("BUGSI_API_URL", raising=False)

        default_path = tmp_path / "default.json"
        default_path.write_text(json.dumps({
            "still_camera": {"type": "arducam_64mp"},
            "event_camera": {"type": "prophesee_genx320"},
        }))

        hw_conf = tmp_path / "hardware.conf"
        hw_conf.write_text("HW_CONFIG=A\n")

        # Local config overrides camera type
        local_path = tmp_path / "local.json"
        local_path.write_text(json.dumps({
            "version": 5,
            "config": {"still_camera": {"type": "custom_cam"}},
        }))

        with mock.patch("bugsi_daemon.config._HARDWARE_CONF_PATH", str(hw_conf)):
            config = ConfigManager(
                default_config_path=default_path,
                local_config_path=local_path,
                credentials_path=tmp_path / "creds.json",
            )
            config.load()

        # Local config wins over hardware override
        assert config.get("still_camera.type") == "custom_cam"
        # But event camera still gets hardware override since local didn't set it
        assert config.get("event_camera.type") == "ids_evs"


class TestSaveCredentials:
    def test_persists_to_file(self, tmp_path, monkeypatch):
        monkeypatch.delenv("BUGSI_API_KEY", raising=False)
        monkeypatch.delenv("BUGSI_API_URL", raising=False)
        default_path = tmp_path / "default.json"
        default_path.write_text(json.dumps({}))
        cred_path = tmp_path / "creds.json"

        config = ConfigManager(
            default_config_path=default_path,
            local_config_path=tmp_path / "local.json",
            credentials_path=cred_path,
        )
        config.load()
        config.save_credentials(api_url="http://new:8000/api/device-data", api_key="new_key")

        assert cred_path.exists()
        saved = json.loads(cred_path.read_text())
        assert saved["api_url"] == "http://new:8000/api/device-data"
        assert saved["api_key"] == "new_key"

    def test_preserves_existing_key_when_only_url_changed(self, tmp_path, monkeypatch):
        monkeypatch.delenv("BUGSI_API_KEY", raising=False)
        monkeypatch.delenv("BUGSI_API_URL", raising=False)
        default_path = tmp_path / "default.json"
        default_path.write_text(json.dumps({}))
        cred_path = tmp_path / "creds.json"
        cred_path.write_text(json.dumps({"api_key": "original_key", "api_url": "http://old:8000/api/device-data"}))

        config = ConfigManager(
            default_config_path=default_path,
            local_config_path=tmp_path / "local.json",
            credentials_path=cred_path,
        )
        config.load()
        config.save_credentials(api_url="http://new:9000/api/device-data")

        saved = json.loads(cred_path.read_text())
        assert saved["api_url"] == "http://new:9000/api/device-data"
        assert saved["api_key"] == "original_key"

    def test_updates_memory(self, tmp_path, monkeypatch):
        monkeypatch.delenv("BUGSI_API_KEY", raising=False)
        monkeypatch.delenv("BUGSI_API_URL", raising=False)
        default_path = tmp_path / "default.json"
        default_path.write_text(json.dumps({}))

        config = ConfigManager(
            default_config_path=default_path,
            local_config_path=tmp_path / "local.json",
            credentials_path=tmp_path / "creds.json",
        )
        config.load()
        config.save_credentials(api_url="http://mem:8000/api/device-data", api_key="mem_key")

        assert config.api_url == "http://mem:8000/api/device-data"
        assert config.api_key == "mem_key"
        assert config.is_configured

    def test_creates_file_if_missing(self, tmp_path, monkeypatch):
        monkeypatch.delenv("BUGSI_API_KEY", raising=False)
        monkeypatch.delenv("BUGSI_API_URL", raising=False)
        default_path = tmp_path / "default.json"
        default_path.write_text(json.dumps({}))
        cred_path = tmp_path / "subdir" / "creds.json"

        config = ConfigManager(
            default_config_path=default_path,
            local_config_path=tmp_path / "local.json",
            credentials_path=cred_path,
        )
        config.load()
        config.save_credentials(api_url="http://new:8000/api/device-data", api_key="k")

        assert cred_path.exists()
        saved = json.loads(cred_path.read_text())
        assert saved["api_url"] == "http://new:8000/api/device-data"

    def test_updates_both_fields(self, tmp_path, monkeypatch):
        monkeypatch.delenv("BUGSI_API_KEY", raising=False)
        monkeypatch.delenv("BUGSI_API_URL", raising=False)
        default_path = tmp_path / "default.json"
        default_path.write_text(json.dumps({}))
        cred_path = tmp_path / "creds.json"
        cred_path.write_text(json.dumps({"api_key": "old_key", "api_url": "http://old:8000/api/device-data"}))

        config = ConfigManager(
            default_config_path=default_path,
            local_config_path=tmp_path / "local.json",
            credentials_path=cred_path,
        )
        config.load()
        config.save_credentials(api_key="new_key", api_url="http://new:9000/api/device-data")

        assert config.api_key == "new_key"
        assert config.api_url == "http://new:9000/api/device-data"
        saved = json.loads(cred_path.read_text())
        assert saved["api_key"] == "new_key"
        assert saved["api_url"] == "http://new:9000/api/device-data"
