"""Tests for the MOG2 adaptive background model in InsectDetector."""

from __future__ import annotations

import numpy as np
import cv2

from detector import InsectDetector


class TestAdaptiveBackground:
    """Tests for the MOG2 background model lifecycle."""

    def test_starts_not_warmed_up(self, default_config: dict) -> None:
        detector = InsectDetector(default_config)
        assert detector.is_warmed_up is False

    def test_warms_up_after_enough_frames(
        self, default_config: dict, white_background: np.ndarray
    ) -> None:
        detector = InsectDetector(default_config)
        warmup = default_config["background"]["warmup_frames"]
        for _ in range(warmup):
            detector.feed_frame(white_background)
        assert detector.is_warmed_up is True

    def test_feed_frame_increments_count(
        self, default_config: dict, white_background: np.ndarray
    ) -> None:
        detector = InsectDetector(default_config)
        detector.feed_frame(white_background)
        assert detector._frames_fed == 1
        detector.feed_frame(white_background)
        assert detector._frames_fed == 2

    def test_detect_also_increments_count(
        self, default_config: dict, white_background: np.ndarray
    ) -> None:
        detector = InsectDetector(default_config)
        detector.detect(white_background)
        assert detector._frames_fed == 1

    def test_reset_clears_model(
        self, default_config: dict, white_background: np.ndarray
    ) -> None:
        detector = InsectDetector(default_config)
        for _ in range(15):
            detector.feed_frame(white_background)
        assert detector.is_warmed_up is True

        detector.reset()
        assert detector.is_warmed_up is False
        assert detector._bg_subtractor is None

    def test_learns_new_background_after_reset(
        self, default_config: dict
    ) -> None:
        """After reset, detector should adapt to a new background."""
        detector = InsectDetector(default_config)
        # Train on white
        white = np.full((480, 640, 3), 230, dtype=np.uint8)
        for _ in range(15):
            detector.feed_frame(white)

        detector.reset()

        # Train on gray
        gray_bg = np.full((480, 640, 3), 128, dtype=np.uint8)
        for _ in range(15):
            detector.feed_frame(gray_bg)

        # Gray frame should now be background (no detections)
        detections = detector.detect(gray_bg.copy())
        assert len(detections) == 0
