"""Tests for the HSV color-based insect classifier."""

from __future__ import annotations

import cv2
import numpy as np

from detector import ColorClassifier


def _make_crop(bgr_color: tuple[int, int, int], size: tuple[int, int] = (50, 40)) -> np.ndarray:
    """Create a uniform-color crop for testing."""
    crop = np.full((size[1], size[0], 3), bgr_color, dtype=np.uint8)
    return crop


class TestColorClassifier:
    """Tests for HSV histogram-based classification."""

    def test_classifies_bee_by_yellow_brown(self, default_config: dict) -> None:
        classifier = ColorClassifier(default_config)
        # Yellow-brown: HSV ~(30, 180, 160) -> BGR ~(40, 130, 180)
        crop = _make_crop((40, 130, 180))
        cls, conf = classifier.classify(crop)
        assert cls == "bee"
        assert conf > 0

    def test_classifies_beetle_by_dark_color(self, default_config: dict) -> None:
        classifier = ColorClassifier(default_config)
        crop = _make_crop((15, 15, 20))
        cls, conf = classifier.classify(crop)
        assert cls == "beetle"
        assert conf > 0

    def test_classifies_moth_by_low_saturation(self, default_config: dict) -> None:
        classifier = ColorClassifier(default_config)
        # Grayish, low saturation
        crop = _make_crop((140, 135, 130))
        cls, conf = classifier.classify(crop)
        assert cls == "moth"
        assert conf > 0

    def test_classifies_butterfly_by_color_variance(self, default_config: dict) -> None:
        classifier = ColorClassifier(default_config)
        # Multi-colored crop simulating a butterfly wing
        crop = np.zeros((80, 100, 3), dtype=np.uint8)
        crop[:40, :50] = (200, 50, 50)   # blue-ish
        crop[:40, 50:] = (50, 200, 200)  # yellow-ish
        crop[40:, :50] = (50, 50, 200)   # red-ish
        crop[40:, 50:] = (200, 200, 50)  # cyan-ish
        cls, conf = classifier.classify(crop)
        assert cls == "butterfly"
        assert conf > 0

    def test_empty_crop_returns_unknown(self, default_config: dict) -> None:
        classifier = ColorClassifier(default_config)
        crop = np.array([], dtype=np.uint8).reshape(0, 0, 3)
        cls, conf = classifier.classify(crop)
        assert cls == "unknown"

    def test_confidence_in_valid_range(self, default_config: dict) -> None:
        classifier = ColorClassifier(default_config)
        for color in [(40, 130, 180), (15, 15, 20), (140, 135, 130)]:
            _, conf = classifier.classify(_make_crop(color))
            assert 0.0 <= conf <= 1.0
