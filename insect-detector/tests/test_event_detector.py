"""Tests for the Prophesee IMX636 event-camera insect detector."""

from __future__ import annotations

import json
import time
from pathlib import Path

import cv2
import numpy as np
import pytest
import yaml

from event_detector import (
    DEFAULT_CONFIG,
    EventDetectorApp,
    _deep_merge,
    build_tracking_config,
    load_config,
    save_config,
)


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


class TestConfig:
    def test_deep_merge_overrides(self) -> None:
        base = {"a": {"b": 1, "c": 2}, "d": 3}
        over = {"a": {"b": 99}, "e": 5}
        result = _deep_merge(base, over)
        assert result == {"a": {"b": 99, "c": 2}, "d": 3, "e": 5}

    def test_deep_merge_does_not_mutate(self) -> None:
        base = {"a": {"b": 1}}
        over = {"a": {"b": 2}}
        _deep_merge(base, over)
        assert base["a"]["b"] == 1

    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "test.yaml"
        save_config(DEFAULT_CONFIG, cfg_path)
        loaded = load_config(cfg_path)
        assert loaded["tracking"]["update_frequency"] == DEFAULT_CONFIG["tracking"]["update_frequency"]
        assert loaded["tracking"]["min_size"] == DEFAULT_CONFIG["tracking"]["min_size"]

    def test_load_creates_default_when_missing(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "sub" / "config.yaml"
        cfg = load_config(cfg_path)
        assert cfg_path.exists()
        assert cfg["alert"]["enabled"] is True

    def test_load_merges_partial_user_config(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "partial.yaml"
        with open(cfg_path, "w") as f:
            yaml.dump({"tracking": {"min_size": 42}}, f)
        cfg = load_config(cfg_path)
        assert cfg["tracking"]["min_size"] == 42
        assert cfg["tracking"]["max_size"] == DEFAULT_CONFIG["tracking"]["max_size"]


# ---------------------------------------------------------------------------
# TrackingConfig builder tests
# ---------------------------------------------------------------------------


class TestBuildTrackingConfig:
    def test_default_config_builds(self) -> None:
        tc = build_tracking_config(DEFAULT_CONFIG)
        assert tc.cell_width == 7
        assert tc.cell_height == 7
        assert tc.min_size == 10
        assert tc.max_size == 300

    def test_custom_sizes(self) -> None:
        cfg = _deep_merge(DEFAULT_CONFIG, {
            "tracking": {"min_size": 20, "max_size": 500, "cell_width": 10},
        })
        tc = build_tracking_config(cfg)
        assert tc.min_size == 20
        assert tc.max_size == 500
        assert tc.cell_width == 10


# ---------------------------------------------------------------------------
# Alert cooldown tests
# ---------------------------------------------------------------------------


class TestAlertCooldown:
    def test_first_alert_fires(self) -> None:
        app = _make_app()
        assert app._alert_ready() is True

    def test_second_alert_blocked_within_cooldown(self) -> None:
        app = _make_app({"alert": {"cooldown_s": 10.0}})
        assert app._alert_ready() is True
        assert app._alert_ready() is False

    def test_alert_fires_after_cooldown(self) -> None:
        app = _make_app({"alert": {"cooldown_s": 0.05}})
        assert app._alert_ready() is True
        time.sleep(0.06)
        assert app._alert_ready() is True


# ---------------------------------------------------------------------------
# Drawing / overlay tests
# ---------------------------------------------------------------------------


class TestDrawTrackingResults:
    def test_draws_boxes(self) -> None:
        img = np.zeros((100, 200, 3), dtype=np.uint8)
        tracks = [{"x": 10, "y": 10, "w": 20, "h": 20, "track_id": 1, "t": 0}]
        EventDetectorApp._draw_tracking_results(img, tracks, 1, False)
        assert img.sum() > 0

    def test_empty_tracks(self) -> None:
        img = np.zeros((100, 200, 3), dtype=np.uint8)
        EventDetectorApp._draw_tracking_results(img, [], 0, False)
        # Status text still drawn
        assert img.sum() > 0

    def test_rec_label(self) -> None:
        img = np.zeros((100, 200, 3), dtype=np.uint8)
        EventDetectorApp._draw_tracking_results(img, [], 0, True)
        assert img.sum() > 0


# ---------------------------------------------------------------------------
# Snapshot tests
# ---------------------------------------------------------------------------


class TestSnapshot:
    def test_snapshot_creates_files(self, tmp_path: Path) -> None:
        app = _make_app({"output": {"snapshot_dir": str(tmp_path)}})
        app.total_detections = 3

        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        tracks = [{"x": 10, "y": 10, "w": 20, "h": 20, "track_id": 5, "t": 0}]
        app._save_snapshot(frame, tracks)

        png_files = list(tmp_path.glob("det_*.png"))
        json_files = list(tmp_path.glob("det_*.json"))
        assert len(png_files) == 1
        assert len(json_files) == 1

        with open(json_files[0]) as f:
            meta = json.load(f)
        assert meta["total_detections"] == 3
        assert len(meta["tracks"]) == 1
        assert meta["tracks"][0]["track_id"] == 5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_args(**overrides):
    """Build a minimal argparse.Namespace for testing."""
    import argparse

    defaults = {
        "input": None,
        "config": None,
        "min_size": None,
        "max_size": None,
        "no_display": True,
        "record": False,
        "verbose": False,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _make_app(cfg_overrides: dict | None = None) -> EventDetectorApp:
    """Build an EventDetectorApp without opening a camera."""
    app = EventDetectorApp.__new__(EventDetectorApp)
    app.cfg = _deep_merge(DEFAULT_CONFIG, cfg_overrides or {})
    app.args = _make_args()
    app.total_detections = 0
    app._known_ids = set()
    app._last_alert = 0.0
    app._writer = None
    return app
