"""Tests for the classical CV insect detection pipeline."""

from __future__ import annotations

import numpy as np
import cv2

from detector import InsectDetector, estimate_size_mm


def _build_warmed_detector(config: dict, background: np.ndarray) -> InsectDetector:
    """Create a detector and warm it up with background frames."""
    # Use a lower MOG2 threshold for test frames (small resolution, uniform bg)
    config = dict(config)
    config["background"] = dict(config.get("background", {}))
    config["background"]["mog2_var_threshold"] = 16
    detector = InsectDetector(config)
    # Feed background frames to build the MOG2 model
    for _ in range(20):
        detector.feed_frame(background)
    return detector


class TestInsectDetectorMOG2:
    """Tests for MOG2-based continuous detection."""

    def test_detects_object_after_warmup(
        self, default_config: dict, white_background: np.ndarray, frame_with_bee: np.ndarray
    ) -> None:
        detector = _build_warmed_detector(default_config, white_background)
        detections = detector.detect(frame_with_bee)
        assert len(detections) >= 1
        assert detections[0].area_px > 0

    def test_empty_frame_returns_no_detections(
        self, default_config: dict, white_background: np.ndarray
    ) -> None:
        detector = _build_warmed_detector(default_config, white_background)
        detections = detector.detect(white_background.copy())
        assert len(detections) == 0

    def test_rejects_too_small_contours(
        self, default_config: dict, white_background: np.ndarray, tiny_noise_frame: np.ndarray
    ) -> None:
        detector = _build_warmed_detector(default_config, white_background)
        detections = detector.detect(tiny_noise_frame)
        assert len(detections) == 0

    def test_rejects_too_large_contours(
        self, default_config: dict, white_background: np.ndarray, large_shadow_frame: np.ndarray
    ) -> None:
        detector = _build_warmed_detector(default_config, white_background)
        detections = detector.detect(large_shadow_frame)
        for d in detections:
            assert d.area_px <= default_config["detection"]["max_contour_area"]

    def test_detection_has_valid_bbox(
        self, default_config: dict, white_background: np.ndarray, frame_with_beetle: np.ndarray
    ) -> None:
        detector = _build_warmed_detector(default_config, white_background)
        detections = detector.detect(frame_with_beetle)
        assert len(detections) >= 1
        x, y, w, h = detections[0].bbox
        assert x >= 0 and y >= 0
        assert w > 0 and h > 0

    def test_is_warmed_up_property(self, default_config: dict, white_background: np.ndarray) -> None:
        detector = InsectDetector(default_config)
        assert detector.is_warmed_up is False
        for _ in range(10):
            detector.feed_frame(white_background)
        assert detector.is_warmed_up is True

    def test_reset_clears_background(self, default_config: dict, white_background: np.ndarray) -> None:
        detector = _build_warmed_detector(default_config, white_background)
        assert detector.is_warmed_up is True
        detector.reset()
        assert detector.is_warmed_up is False


class TestInsectDetectorStatic:
    """Tests for static single-frame detection (no background history needed)."""

    def test_detects_object_on_uniform_background(
        self, default_config: dict, frame_with_bee: np.ndarray
    ) -> None:
        detector = InsectDetector(default_config)
        detections = detector.detect_static(frame_with_bee)
        assert len(detections) >= 1

    def test_detects_dark_object(
        self, default_config: dict, frame_with_beetle: np.ndarray
    ) -> None:
        detector = InsectDetector(default_config)
        detections = detector.detect_static(frame_with_beetle)
        assert len(detections) >= 1

    def test_empty_uniform_frame_no_detections(self, default_config: dict) -> None:
        detector = InsectDetector(default_config)
        uniform = np.full((480, 640, 3), 200, dtype=np.uint8)
        detections = detector.detect_static(uniform)
        assert len(detections) == 0

    def test_detection_has_positive_size_estimate(
        self, default_config: dict, frame_with_bee: np.ndarray
    ) -> None:
        detector = InsectDetector(default_config)
        detections = detector.detect_static(frame_with_bee)
        assert len(detections) >= 1
        assert detections[0].estimated_size_mm > 0

    def test_detection_confidence_in_range(
        self, default_config: dict, frame_with_bee: np.ndarray
    ) -> None:
        detector = InsectDetector(default_config)
        detections = detector.detect_static(frame_with_bee)
        for d in detections:
            assert 0.0 <= d.confidence <= 1.0


class TestSizeEstimation:
    """Tests for real-world size estimation from pixel area."""

    def test_returns_positive_value(self, default_config: dict) -> None:
        size = estimate_size_mm(1000, 3840, default_config)
        assert size > 0

    def test_larger_area_gives_larger_size(self, default_config: dict) -> None:
        small = estimate_size_mm(500, 3840, default_config)
        large = estimate_size_mm(5000, 3840, default_config)
        assert large > small

    def test_reasonable_range_for_insect(self, default_config: dict) -> None:
        # A typical bee at 4K might be ~800-2000 px area
        size = estimate_size_mm(1200, 3840, default_config)
        # Should be in plausible insect range (1-100mm)
        assert 1 <= size <= 100
