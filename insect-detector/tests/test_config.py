"""Tests for configuration loading."""

from __future__ import annotations

import json
from pathlib import Path

from detector import load_config, _cfg


class TestConfig:
    """Tests for config loading and dotted key access."""

    def test_load_default_config(self) -> None:
        config = load_config()
        assert "camera" in config
        assert "detection" in config
        assert "scheduling" in config

    def test_load_custom_config(self, tmp_path: Path) -> None:
        custom = {"camera": {"resolution_width": 1920}}
        config_file = tmp_path / "custom.json"
        config_file.write_text(json.dumps(custom))
        config = load_config(config_file)
        assert config["camera"]["resolution_width"] == 1920

    def test_load_missing_file_returns_empty(self, tmp_path: Path) -> None:
        config = load_config(tmp_path / "nonexistent.json")
        assert config == {}

    def test_cfg_dotted_key(self) -> None:
        config = {"camera": {"resolution_width": 3840}}
        assert _cfg(config, "camera.resolution_width") == 3840

    def test_cfg_missing_key_returns_default(self) -> None:
        config = {"camera": {}}
        assert _cfg(config, "camera.missing_key", 42) == 42

    def test_cfg_deeply_nested(self) -> None:
        config = {"a": {"b": {"c": 99}}}
        assert _cfg(config, "a.b.c") == 99
