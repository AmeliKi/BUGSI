"""Tests for detection logging and crop saving."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from detector import Detection, DetectionLogger


def _make_detection(**kwargs) -> Detection:
    defaults = {
        "bbox": (100, 100, 50, 40),
        "confidence": 0.8,
        "insect_class": "bee",
        "area_px": 1500,
        "estimated_size_mm": 12.0,
    }
    defaults.update(kwargs)
    return Detection(**defaults)


class TestDetectionLogger:
    """Tests for JSONL logging and crop saving."""

    def test_creates_output_directory(self, default_config: dict, tmp_path: Path) -> None:
        config = dict(default_config)
        config["output"] = dict(config["output"])
        config["output"]["output_dir"] = str(tmp_path / "out")

        DetectionLogger(config)

        assert (tmp_path / "out").is_dir()
        assert (tmp_path / "out" / "crops").is_dir()

    def test_logs_jsonl_format(self, default_config: dict, tmp_path: Path) -> None:
        config = dict(default_config)
        config["output"] = dict(config["output"])
        config["output"]["output_dir"] = str(tmp_path / "out")
        config["output"]["save_crops"] = False

        logger = DetectionLogger(config)
        frame = np.full((480, 640, 3), 200, dtype=np.uint8)
        det = _make_detection()

        logger.log(frame, [det], processing_time_ms=50.0)

        log_file = tmp_path / "out" / "detections.jsonl"
        assert log_file.exists()
        line = log_file.read_text().strip()
        record = json.loads(line)

        assert record["total_count"] == 1
        assert record["processing_time_ms"] == 50.0
        assert record["detections"][0]["class"] == "bee"
        assert "timestamp" in record

    def test_saves_crop_images(self, default_config: dict, tmp_path: Path) -> None:
        config = dict(default_config)
        config["output"] = dict(config["output"])
        config["output"]["output_dir"] = str(tmp_path / "out")
        config["output"]["save_crops"] = True

        logger = DetectionLogger(config)
        frame = np.full((480, 640, 3), 200, dtype=np.uint8)
        det = _make_detection()

        logger.log(frame, [det], processing_time_ms=30.0)

        crops = list((tmp_path / "out" / "crops").glob("*.jpg"))
        assert len(crops) == 1

    def test_empty_detections_still_logs(self, default_config: dict, tmp_path: Path) -> None:
        config = dict(default_config)
        config["output"] = dict(config["output"])
        config["output"]["output_dir"] = str(tmp_path / "out")

        logger = DetectionLogger(config)
        frame = np.full((480, 640, 3), 200, dtype=np.uint8)

        logger.log(frame, [], processing_time_ms=10.0)

        log_file = tmp_path / "out" / "detections.jsonl"
        record = json.loads(log_file.read_text().strip())
        assert record["total_count"] == 0
        assert record["detections"] == []

    def test_battery_soc_logged(self, default_config: dict, tmp_path: Path) -> None:
        config = dict(default_config)
        config["output"] = dict(config["output"])
        config["output"]["output_dir"] = str(tmp_path / "out")
        config["output"]["save_crops"] = False

        logger = DetectionLogger(config)
        frame = np.full((480, 640, 3), 200, dtype=np.uint8)

        logger.log(frame, [], processing_time_ms=5.0, battery_soc=72.5)

        record = json.loads((tmp_path / "out" / "detections.jsonl").read_text().strip())
        assert record["battery_soc"] == 72.5
