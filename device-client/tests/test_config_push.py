from __future__ import annotations

import json

import pytest

from bugsi_daemon.config import ConfigManager


@pytest.fixture
def config(tmp_path):
    default_path = tmp_path / "default.json"
    default_path.write_text(json.dumps({
        "telemetry": {"collection_interval_minutes": 5},
        "upload": {"interval_minutes": 60},
    }))
    local_path = tmp_path / "local.json"
    cred_path = tmp_path / "cred.json"
    cm = ConfigManager(
        default_config_path=default_path,
        local_config_path=str(local_path),
        credentials_path=str(cred_path),
    )
    cm.load()
    return cm


def test_apply_local_bumps_version(config):
    assert config.version == 0
    new_version = config.apply_local({"telemetry": {"collection_interval_minutes": 10}})
    assert new_version == 1
    assert config.version == 1
    assert config.get("telemetry.collection_interval_minutes") == 10


def test_apply_local_sets_unpushed(config):
    assert not config.has_unpushed_changes
    config.apply_local({"telemetry": {"collection_interval_minutes": 10}})
    assert config.has_unpushed_changes


def test_clear_unpushed(config):
    config.apply_local({"telemetry": {"collection_interval_minutes": 10}})
    assert config.has_unpushed_changes
    config.clear_unpushed()
    assert not config.has_unpushed_changes


def test_apply_local_persists(config, tmp_path):
    config.apply_local({"telemetry": {"collection_interval_minutes": 10}})

    # Load a fresh config from the same paths
    cm2 = ConfigManager(
        default_config_path=tmp_path / "default.json",
        local_config_path=str(tmp_path / "local.json"),
        credentials_path=str(tmp_path / "cred.json"),
    )
    cm2.load()
    assert cm2.version == 1
    assert cm2.get("telemetry.collection_interval_minutes") == 10


def test_apply_local_deep_merges(config):
    config.apply_local({"upload": {"max_batch_size": 200}})
    # Original field should still exist
    assert config.get("upload.interval_minutes") == 60
    # New field should be set
    assert config.get("upload.max_batch_size") == 200


def test_multiple_local_applies_increment(config):
    config.apply_local({"a": 1})
    config.apply_local({"b": 2})
    config.apply_local({"c": 3})
    assert config.version == 3
    assert config.get("a") == 1
    assert config.get("b") == 2
    assert config.get("c") == 3
