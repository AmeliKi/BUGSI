"""Shared fixtures for insect detector tests."""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest


@pytest.fixture
def default_config() -> dict:
    """Load the default config."""
    config_path = Path(__file__).parent.parent / "config" / "defaults.json"
    with open(config_path) as f:
        return json.load(f)


@pytest.fixture
def white_background() -> np.ndarray:
    """A 640x480 white frame simulating the contrast screen with no insects."""
    return np.full((480, 640, 3), 230, dtype=np.uint8)


@pytest.fixture
def frame_with_bee(white_background: np.ndarray) -> np.ndarray:
    """White background with a yellow-brown ellipse (simulated bee)."""
    frame = white_background.copy()
    # HSV(30, 180, 160) -> yellow-brown in BGR
    color_bgr = (40, 130, 180)  # brownish-yellow
    cv2.ellipse(frame, (320, 240), (25, 15), 0, 0, 360, color_bgr, -1)
    return frame


@pytest.fixture
def frame_with_beetle(white_background: np.ndarray) -> np.ndarray:
    """White background with a dark ellipse (simulated beetle)."""
    frame = white_background.copy()
    color_bgr = (20, 20, 25)  # very dark
    cv2.ellipse(frame, (300, 200), (20, 15), 30, 0, 360, color_bgr, -1)
    return frame


@pytest.fixture
def frame_with_butterfly(white_background: np.ndarray) -> np.ndarray:
    """White background with a large colorful shape (simulated butterfly)."""
    frame = white_background.copy()
    # Large, colorful - draw multi-colored wings
    cv2.ellipse(frame, (320, 240), (60, 40), 0, 0, 360, (200, 50, 50), -1)
    cv2.ellipse(frame, (310, 230), (30, 20), 0, 0, 360, (50, 200, 200), -1)
    cv2.ellipse(frame, (330, 250), (25, 18), 0, 0, 360, (50, 50, 200), -1)
    return frame


@pytest.fixture
def frame_with_moth(white_background: np.ndarray) -> np.ndarray:
    """White background with a pale, low-saturation shape (simulated moth)."""
    frame = white_background.copy()
    color_bgr = (160, 155, 150)  # grayish, low saturation
    cv2.ellipse(frame, (320, 240), (30, 20), 10, 0, 360, color_bgr, -1)
    return frame


@pytest.fixture
def frame_empty(white_background: np.ndarray) -> np.ndarray:
    """Same as background — no insects."""
    return white_background.copy()


@pytest.fixture
def tiny_noise_frame(white_background: np.ndarray) -> np.ndarray:
    """Background with a tiny dark speck (below min contour area)."""
    frame = white_background.copy()
    cv2.circle(frame, (300, 200), 3, (10, 10, 10), -1)  # ~28 px area
    return frame


@pytest.fixture
def large_shadow_frame(white_background: np.ndarray) -> np.ndarray:
    """Background with a huge shadow (above max contour area)."""
    frame = white_background.copy()
    cv2.rectangle(frame, (50, 50), (550, 400), (100, 100, 100), -1)
    return frame
