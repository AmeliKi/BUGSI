"""
BUGSI Insect Detector — Classical CV approach.

Standalone script for Raspberry Pi 5 + Arducam 64MP.
Detects insects via adaptive background subtraction (MOG2) + contour analysis,
classifies by color histogram, and logs results as JSONL.

No manual calibration required — the background model learns automatically.

Usage:
    python detector.py                       # Run continuous detection loop
    python detector.py --single              # Single capture + detect
    python detector.py --mock                # Use mock camera (for development)
    python detector.py --config my_conf.json # Custom config file

Dependencies:
    pip install opencv-python-headless numpy picamera2
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np

logger = logging.getLogger("bugsi-detector")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG = Path(__file__).parent / "config" / "defaults.json"


def load_config(path: str | Path | None = None) -> dict:
    """Load config from JSON file, falling back to defaults."""
    config_path = Path(path) if path else _DEFAULT_CONFIG
    if config_path.exists():
        with open(config_path) as f:
            return json.load(f)
    logger.warning("Config not found at %s, using built-in defaults", config_path)
    return {}


def _cfg(config: dict, dotted_key: str, default=None):
    """Read a dotted key from nested dict, e.g. 'camera.resolution_width'."""
    keys = dotted_key.split(".")
    val = config
    for k in keys:
        if isinstance(val, dict) and k in val:
            val = val[k]
        else:
            return default
    return val


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class Detection:
    """A single insect detection."""

    bbox: tuple[int, int, int, int]  # x, y, w, h
    confidence: float
    insect_class: str
    area_px: int
    estimated_size_mm: float
    contour: np.ndarray | None = field(default=None, repr=False)


# ---------------------------------------------------------------------------
# Camera abstraction
# ---------------------------------------------------------------------------


class CameraInterface(Protocol):
    """Minimal camera interface for capture."""

    def open(self) -> None: ...
    def close(self) -> None: ...
    def capture(self) -> np.ndarray: ...
    def is_open(self) -> bool: ...


class ArducamCapture:
    """Picamera2 wrapper for Arducam 64MP on Raspberry Pi 5."""

    def __init__(self, config: dict) -> None:
        self._config = config
        self._picam2 = None
        self._width = _cfg(config, "camera.resolution_width", 3840)
        self._height = _cfg(config, "camera.resolution_height", 2160)

    def open(self) -> None:
        if self._picam2 is not None:
            return
        from picamera2 import Picamera2

        self._picam2 = Picamera2(camera_num=_cfg(self._config, "camera.camera_id", 1))
        still_config = self._picam2.create_still_configuration(
            main={"size": (self._width, self._height), "format": "BGR888"},
        )
        self._picam2.configure(still_config)

        af_mode = _cfg(self._config, "camera.autofocus_mode", "continuous")
        if af_mode == "continuous":
            from libcamera import controls

            self._picam2.set_controls({"AfMode": controls.AfModeEnum.Continuous})

        self._picam2.start()
        # Let AE/AWB/AF settle
        time.sleep(1.0)

    def close(self) -> None:
        if self._picam2 is not None:
            self._picam2.stop()
            self._picam2.close()
            self._picam2 = None

    def capture(self) -> np.ndarray:
        if self._picam2 is None:
            raise RuntimeError("Camera not open. Call open() first.")
        return self._picam2.capture_array("main")

    def is_open(self) -> bool:
        return self._picam2 is not None


class MockCamera:
    """Mock camera for development/testing without hardware."""

    def __init__(self, config: dict) -> None:
        self._width = _cfg(config, "camera.resolution_width", 3840)
        self._height = _cfg(config, "camera.resolution_height", 2160)
        self._open = False
        self._frame_count = 0

    def open(self) -> None:
        self._open = True
        logger.info("Mock camera opened (%dx%d)", self._width, self._height)

    def close(self) -> None:
        self._open = False

    def capture(self) -> np.ndarray:
        if not self._open:
            raise RuntimeError("Mock camera not open.")
        # Light background with random synthetic "insects"
        frame = np.full((self._height, self._width, 3), 230, dtype=np.uint8)
        rng = np.random.default_rng(seed=self._frame_count)
        n_insects = rng.integers(0, 4)
        for _ in range(n_insects):
            cx = rng.integers(100, self._width - 100)
            cy = rng.integers(100, self._height - 100)
            axes = (rng.integers(10, 60), rng.integers(8, 40))
            color = (
                int(rng.integers(0, 180)),
                int(rng.integers(40, 200)),
                int(rng.integers(20, 180)),
            )
            cv2.ellipse(frame, (int(cx), int(cy)), axes, float(rng.integers(0, 360)), 0, 360, color, -1)
        self._frame_count += 1
        return frame

    def is_open(self) -> bool:
        return self._open


# ---------------------------------------------------------------------------
# Insect classifier (color histogram)
# ---------------------------------------------------------------------------


class ColorClassifier:
    """Classify insect crops by HSV color histogram analysis."""

    def __init__(self, config: dict) -> None:
        self._cfg = _cfg(config, "classification", {})

    def classify(self, crop_bgr: np.ndarray) -> tuple[str, float]:
        """Return (class_name, confidence) for the given BGR crop."""
        if crop_bgr.size == 0:
            return "unknown", 0.0

        hsv = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2HSV)
        h, s, v = cv2.split(hsv)

        mean_h = float(np.mean(h))
        mean_s = float(np.mean(s))
        mean_v = float(np.mean(v))
        std_h = float(np.std(h))
        area = crop_bgr.shape[0] * crop_bgr.shape[1]

        # Color std across all channels — high variance = butterfly
        color_std = float(np.std(hsv))

        bee_hue_min = self._cfg.get("bee_hue_min", 15)
        bee_hue_max = self._cfg.get("bee_hue_max", 45)
        bee_sat_min = self._cfg.get("bee_sat_min", 80)
        beetle_value_max = self._cfg.get("beetle_value_max", 80)
        moth_sat_max = self._cfg.get("moth_sat_max", 100)
        butterfly_min_area = self._cfg.get("butterfly_min_area", 3000)
        butterfly_color_std_min = self._cfg.get("butterfly_color_std_min", 30)

        # Decision tree based on dominant color features
        # Beetle: very dark overall (check first — darkness is most distinctive)
        if mean_v <= beetle_value_max:
            confidence = min(1.0, 1.0 - mean_v / 255)
            return "beetle", round(confidence, 2)

        # Bee: yellow-brown hue, high saturation
        if bee_hue_min <= mean_h <= bee_hue_max and mean_s >= bee_sat_min:
            confidence = min(1.0, mean_s / 180)
            return "bee", round(confidence, 2)

        # Butterfly: large area, high color variance
        if area >= butterfly_min_area and color_std >= butterfly_color_std_min:
            confidence = min(1.0, color_std / 60)
            return "butterfly", round(confidence, 2)

        # Moth: similar to butterfly but low saturation, smaller
        if mean_s <= moth_sat_max:
            confidence = min(1.0, 1.0 - mean_s / 180)
            return "moth", round(confidence, 2)

        # Wasp: narrow body (handled by aspect ratio), yellow-black pattern
        if std_h > 20 and bee_hue_min <= mean_h <= bee_hue_max + 10:
            confidence = min(1.0, std_h / 50)
            return "wasp", round(confidence, 2)

        return "unknown", 0.3


# ---------------------------------------------------------------------------
# Size estimation
# ---------------------------------------------------------------------------


def estimate_size_mm(
    area_px: int, frame_width: int, config: dict
) -> float:
    """Estimate real-world size (mm) from pixel area.

    Uses the known sensor width, focal length, and distance to compute
    the ground sampling distance (GSD) and then approximate body length
    from pixel area (assuming roughly circular).
    """
    distance_cm = _cfg(config, "size_estimation.distance_cm", 40)
    sensor_width_mm = _cfg(config, "size_estimation.sensor_width_mm", 6.287)
    focal_length_mm = _cfg(config, "size_estimation.focal_length_mm", 4.74)

    # Field of view width at the given distance (in mm)
    fov_width_mm = (sensor_width_mm * distance_cm * 10) / focal_length_mm
    # Pixels per mm
    px_per_mm = frame_width / fov_width_mm
    # Approximate body length as diameter of equivalent circle
    radius_px = np.sqrt(area_px / np.pi)
    diameter_mm = (2 * radius_px) / px_per_mm
    return round(float(diameter_mm), 1)


# ---------------------------------------------------------------------------
# Detection pipeline
# ---------------------------------------------------------------------------


def _filter_contours(
    contours: list,
    frame: np.ndarray,
    config: dict,
    classifier: ColorClassifier,
) -> list[Detection]:
    """Shared contour filtering + classification logic."""
    det = _cfg(config, "detection", {})
    min_area = det.get("min_contour_area", 200)
    max_area = det.get("max_contour_area", 50000)
    min_aspect = det.get("min_aspect_ratio", 0.2)
    max_aspect = det.get("max_aspect_ratio", 5.0)
    min_solidity = det.get("min_solidity", 0.3)

    h_frame, w_frame = frame.shape[:2]
    detections: list[Detection] = []

    for contour in contours:
        area = cv2.contourArea(contour)
        if area < min_area or area > max_area:
            continue

        x, y, w, h = cv2.boundingRect(contour)

        aspect = w / h if h > 0 else 0
        if aspect < min_aspect or aspect > max_aspect:
            continue

        hull = cv2.convexHull(contour)
        hull_area = cv2.contourArea(hull)
        solidity = area / hull_area if hull_area > 0 else 0
        if solidity < min_solidity:
            continue

        # Extract crop for classification
        pad = 5
        x1 = max(0, x - pad)
        y1 = max(0, y - pad)
        x2 = min(w_frame, x + w + pad)
        y2 = min(h_frame, y + h + pad)
        crop = frame[y1:y2, x1:x2]

        insect_class, confidence = classifier.classify(crop)
        size_mm = estimate_size_mm(area, w_frame, config)

        detections.append(
            Detection(
                bbox=(x, y, w, h),
                confidence=confidence,
                insect_class=insect_class,
                area_px=int(area),
                estimated_size_mm=size_mm,
                contour=contour,
            )
        )

    return detections


class InsectDetector:
    """Classical CV insect detector using MOG2 adaptive background subtraction.

    Two detection modes:
    - Continuous (default): Uses MOG2 which learns the background automatically
      over time. No calibration needed. Best for the main capture loop.
    - Static (for single captures): Uses adaptive thresholding to find objects
      that contrast against their surroundings. Works without any history.
    """

    def __init__(self, config: dict) -> None:
        self._config = config
        self._classifier = ColorClassifier(config)

        det = _cfg(config, "detection", {})
        self._morph_kernel = det.get("morph_kernel_size", 5)
        self._morph_iter = det.get("morph_iterations", 2)
        self._blur_kernel = det.get("blur_kernel_size", 5)

        bg = _cfg(config, "background", {})
        self._mog2_history = bg.get("mog2_history", 100)
        self._mog2_threshold = bg.get("mog2_var_threshold", 40)
        self._mog2_shadow = bg.get("mog2_detect_shadows", False)
        self._warmup_frames = bg.get("warmup_frames", 10)

        self._bg_subtractor: cv2.BackgroundSubtractorMOG2 | None = None
        self._frames_fed = 0

    def _get_subtractor(self) -> cv2.BackgroundSubtractorMOG2:
        """Lazily create the MOG2 background subtractor."""
        if self._bg_subtractor is None:
            self._bg_subtractor = cv2.createBackgroundSubtractorMOG2(
                history=self._mog2_history,
                varThreshold=self._mog2_threshold,
                detectShadows=self._mog2_shadow,
            )
            self._frames_fed = 0
        return self._bg_subtractor

    @property
    def is_warmed_up(self) -> bool:
        """True once enough frames have been fed for reliable detection."""
        return self._frames_fed >= self._warmup_frames

    def feed_frame(self, frame: np.ndarray) -> None:
        """Feed a frame to the background model without detecting.

        Useful during warmup to build the background model quickly.
        """
        sub = self._get_subtractor()
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray_blur = cv2.GaussianBlur(gray, (self._blur_kernel, self._blur_kernel), 0)
        sub.apply(gray_blur)
        self._frames_fed += 1

    def detect(self, frame: np.ndarray) -> list[Detection]:
        """Detect insects using MOG2 adaptive background subtraction.

        The background model learns continuously — no manual calibration needed.
        During the first few frames (warmup), results may include false positives
        as the model is still learning the scene.
        """
        sub = self._get_subtractor()
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray_blur = cv2.GaussianBlur(gray, (self._blur_kernel, self._blur_kernel), 0)

        # Apply MOG2 — returns foreground mask (255=foreground, 127=shadow, 0=background)
        fg_mask = sub.apply(gray_blur)
        self._frames_fed += 1

        # Remove shadows (127) — keep only definite foreground (255)
        _, binary = cv2.threshold(fg_mask, 200, 255, cv2.THRESH_BINARY)

        # Morphological ops to clean up noise
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (self._morph_kernel, self._morph_kernel)
        )
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)
        binary = cv2.dilate(binary, kernel, iterations=self._morph_iter)
        binary = cv2.erode(binary, kernel, iterations=max(1, self._morph_iter - 1))

        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        return _filter_contours(contours, frame, self._config, self._classifier)

    def detect_static(self, frame: np.ndarray) -> list[Detection]:
        """Detect insects in a single frame without any background history.

        Uses adaptive thresholding to find objects that stand out from
        their local surroundings. Works for any scene — no calibration,
        no prior frames needed.
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray_blur = cv2.GaussianBlur(gray, (self._blur_kernel, self._blur_kernel), 0)

        # Adaptive threshold: highlights regions darker/lighter than local mean
        # blockSize must be odd and > 1
        block_size = max(3, (min(frame.shape[:2]) // 20) | 1)
        binary = cv2.adaptiveThreshold(
            gray_blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, block_size, 10,
        )

        # Also find regions via Otsu on the overall difference from median
        median_val = int(np.median(gray_blur))
        diff = cv2.absdiff(gray_blur, np.full_like(gray_blur, median_val))
        _, otsu_binary = cv2.threshold(diff, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # Combine both masks — union gives better coverage
        combined = cv2.bitwise_or(binary, otsu_binary)

        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (self._morph_kernel, self._morph_kernel)
        )
        combined = cv2.morphologyEx(combined, cv2.MORPH_OPEN, kernel, iterations=1)
        combined = cv2.dilate(combined, kernel, iterations=self._morph_iter)
        combined = cv2.erode(combined, kernel, iterations=max(1, self._morph_iter - 1))

        contours, _ = cv2.findContours(combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        return _filter_contours(contours, frame, self._config, self._classifier)

    def reset(self) -> None:
        """Reset the background model (e.g. after a long pause)."""
        self._bg_subtractor = None
        self._frames_fed = 0


# ---------------------------------------------------------------------------
# Adaptive scheduler
# ---------------------------------------------------------------------------


class AdaptiveScheduler:
    """Adjusts capture interval based on time-of-day, activity, and battery."""

    def __init__(self, config: dict) -> None:
        sched = _cfg(config, "scheduling", {})
        self._base_interval = sched.get("capture_interval_seconds", 30)
        self._min_interval = sched.get("min_interval_seconds", 10)
        self._max_interval = sched.get("max_interval_seconds", 300)
        self._adaptive = sched.get("adaptive", True)
        self._night_start = sched.get("night_start_hour", 22)
        self._night_end = sched.get("night_end_hour", 6)
        self._peak_start = sched.get("peak_start_hour", 9)
        self._peak_end = sched.get("peak_end_hour", 16)
        self._peak_interval = sched.get("peak_interval_seconds", 15)
        self._backoff = sched.get("no_detection_backoff_factor", 1.5)
        self._speedup = sched.get("detection_speedup_factor", 0.5)

        self._current_interval = float(self._base_interval)
        self._consecutive_empty = 0

    def is_night(self, hour: int | None = None) -> bool:
        """Return True if current time is in the night window (no captures)."""
        h = hour if hour is not None else datetime.now().hour
        if self._night_start > self._night_end:
            return h >= self._night_start or h < self._night_end
        return self._night_start <= h < self._night_end

    def is_peak(self, hour: int | None = None) -> bool:
        """Return True if current time is in peak insect activity window."""
        h = hour if hour is not None else datetime.now().hour
        return self._peak_start <= h < self._peak_end

    def get_next_interval(self, detection_count: int, battery_soc: float | None = None) -> float:
        """Compute next capture interval in seconds."""
        if not self._adaptive:
            return float(self._base_interval)

        # Start from time-of-day baseline
        if self.is_peak():
            base = float(self._peak_interval)
        else:
            base = float(self._base_interval)

        # Adjust based on recent activity
        if detection_count > 0:
            self._consecutive_empty = 0
            interval = base * self._speedup
        else:
            self._consecutive_empty += 1
            interval = base * (self._backoff ** min(self._consecutive_empty, 5))

        # Battery conservation: increase interval when battery is low
        if battery_soc is not None and battery_soc < 30:
            low_factor = 1.0 + (30 - battery_soc) / 15  # up to 3x at 0%
            interval *= low_factor

        return max(self._min_interval, min(self._max_interval, interval))

    def should_shutdown(self, battery_soc: float, threshold: float = 5.0) -> bool:
        """Return True if battery is critically low."""
        return battery_soc <= threshold


# ---------------------------------------------------------------------------
# Power monitor
# ---------------------------------------------------------------------------


class PowerMonitor:
    """Read battery SoC from a file (shared with the daemon) or return None."""

    def __init__(self, config: dict) -> None:
        self._soc_file = Path(_cfg(config, "power.battery_soc_file", "/tmp/bugsi_battery_soc"))
        self._governor_path = Path(
            _cfg(config, "power.cpu_governor_path",
                 "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
        )

    def read_soc(self) -> float | None:
        """Read battery state of charge (0-100). Returns None if unavailable."""
        try:
            return float(self._soc_file.read_text().strip())
        except (FileNotFoundError, ValueError):
            return None

    def set_cpu_governor(self, governor: str) -> None:
        """Set CPU frequency governor (powersave/performance). Requires root."""
        try:
            self._governor_path.write_text(governor)
            logger.debug("CPU governor set to %s", governor)
        except PermissionError:
            logger.debug("Cannot set CPU governor (not root)")
        except FileNotFoundError:
            pass


# ---------------------------------------------------------------------------
# Output (JSONL logger + crop saver)
# ---------------------------------------------------------------------------


class DetectionLogger:
    """Write detection results to a JSONL log file."""

    def __init__(self, config: dict) -> None:
        out = _cfg(config, "output", {})
        self._output_dir = Path(out.get("output_dir", "detections"))
        self._log_file = self._output_dir / out.get("log_file", "detections.jsonl")
        self._save_crops = out.get("save_crops", True)
        self._save_full = out.get("save_full_frame", False)
        self._quality = _cfg(config, "camera.jpeg_quality", 85)

        self._output_dir.mkdir(parents=True, exist_ok=True)
        (self._output_dir / "crops").mkdir(exist_ok=True)
        if self._save_full:
            (self._output_dir / "frames").mkdir(exist_ok=True)

    def log(
        self,
        frame: np.ndarray,
        detections: list[Detection],
        processing_time_ms: float,
        battery_soc: float | None = None,
    ) -> None:
        """Log detections to JSONL and save crops."""
        ts = datetime.now(timezone.utc)
        frame_id = f"cap_{ts.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

        det_records = []
        for i, det in enumerate(detections):
            crop_path = None
            if self._save_crops:
                crop_path = self._save_crop(frame, det, frame_id, i)
            det_records.append({
                "id": i,
                "bbox": list(det.bbox),
                "confidence": det.confidence,
                "class": det.insect_class,
                "area_px": det.area_px,
                "estimated_size_mm": det.estimated_size_mm,
                "crop_path": crop_path,
            })

        frame_path = None
        if self._save_full:
            frame_path = str(self._output_dir / "frames" / f"{frame_id}.jpg")
            cv2.imwrite(frame_path, frame, [cv2.IMWRITE_JPEG_QUALITY, self._quality])

        record = {
            "timestamp": ts.isoformat(),
            "frame_id": frame_id,
            "total_count": len(detections),
            "detections": det_records,
            "processing_time_ms": round(processing_time_ms, 1),
            "battery_soc": battery_soc,
            "frame_path": frame_path,
        }

        with open(self._log_file, "a") as f:
            f.write(json.dumps(record) + "\n")

        if detections:
            logger.info(
                "Detected %d insect(s): %s",
                len(detections),
                ", ".join(f"{d.insect_class}({d.confidence})" for d in detections),
            )

    def _save_crop(
        self, frame: np.ndarray, det: Detection, frame_id: str, idx: int
    ) -> str:
        x, y, w, h = det.bbox
        pad = 10
        fh, fw = frame.shape[:2]
        x1 = max(0, x - pad)
        y1 = max(0, y - pad)
        x2 = min(fw, x + w + pad)
        y2 = min(fh, y + h + pad)
        crop = frame[y1:y2, x1:x2]

        crop_path = str(self._output_dir / "crops" / f"{frame_id}_det{idx}.jpg")
        cv2.imwrite(crop_path, crop, [cv2.IMWRITE_JPEG_QUALITY, self._quality])
        return crop_path


# ---------------------------------------------------------------------------
# Main capture loop
# ---------------------------------------------------------------------------


def run_single_capture(
    camera: CameraInterface, config: dict
) -> list[Detection]:
    """Capture one frame, detect using static mode, print results."""
    detector = InsectDetector(config)
    det_logger = DetectionLogger(config)

    camera.open()
    try:
        frame = camera.capture()
        t0 = time.monotonic()
        detections = detector.detect_static(frame)
        elapsed_ms = (time.monotonic() - t0) * 1000

        det_logger.log(frame, detections, elapsed_ms)

        if detections:
            for d in detections:
                print(
                    f"  {d.insect_class} (conf={d.confidence}, "
                    f"size~{d.estimated_size_mm}mm, area={d.area_px}px)"
                )
        else:
            print("  No insects detected.")

        return detections
    finally:
        camera.close()


def run_loop(camera: CameraInterface, config: dict) -> None:
    """Main continuous detection loop with adaptive MOG2 background model."""
    detector = InsectDetector(config)
    det_logger = DetectionLogger(config)
    scheduler = AdaptiveScheduler(config)
    power = PowerMonitor(config)

    running = True

    def _handle_signal(sig, _frame):
        nonlocal running
        logger.info("Received signal %s, shutting down...", sig)
        running = False

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    warmup_needed = _cfg(config, "background.warmup_frames", 10)
    warmup_interval = _cfg(config, "background.warmup_interval_seconds", 2)

    logger.info("Starting detection loop (Ctrl+C to stop)")
    logger.info("Background model will warm up over the first %d frames", warmup_needed)

    # --- Warmup phase: keep camera open, feed frames rapidly ---
    if warmup_needed > 0:
        logger.info("Warmup: capturing %d frames with %ds interval...", warmup_needed, warmup_interval)
        power.set_cpu_governor("performance")
        camera.open()
        try:
            while running and not detector.is_warmed_up:
                if scheduler.is_night():
                    logger.info("Night mode during warmup — deferring")
                    break
                frame = camera.capture()
                detector.feed_frame(frame)
                logger.debug(
                    "Warmup frame %d/%d",
                    detector._frames_fed, detector._warmup_frames,
                )
                if not detector.is_warmed_up:
                    time.sleep(warmup_interval)
        except Exception as e:
            logger.error("Warmup capture failed: %s", e)
        finally:
            camera.close()
            power.set_cpu_governor("powersave")

        if detector.is_warmed_up:
            logger.info("Warmup complete — background model ready")

    # --- Main detection loop ---
    while running:
        # Night check
        if scheduler.is_night():
            logger.debug("Night mode — sleeping 60s")
            # Reset background model after night gap so it re-learns in the morning
            detector.reset()
            time.sleep(60)
            continue

        # Battery check
        soc = power.read_soc()
        if soc is not None:
            low_threshold = _cfg(config, "power.low_battery_soc_threshold", 15.0)
            crit_threshold = _cfg(config, "power.critical_battery_soc_threshold", 5.0)
            if scheduler.should_shutdown(soc, crit_threshold):
                logger.warning("Critical battery (%.1f%%) — shutting down", soc)
                break
            if soc < low_threshold:
                logger.info("Low battery (%.1f%%) — extending intervals", soc)

        # Capture
        power.set_cpu_governor("performance")
        camera.open()
        try:
            frame = camera.capture()
        except Exception as e:
            logger.error("Capture failed: %s", e)
            camera.close()
            time.sleep(5)
            continue

        # Detect — MOG2 learns the background automatically
        t0 = time.monotonic()
        detections = detector.detect(frame)
        elapsed_ms = (time.monotonic() - t0) * 1000

        # Log
        det_logger.log(frame, detections, elapsed_ms, soc)

        camera.close()
        power.set_cpu_governor("powersave")

        # Schedule next capture
        interval = scheduler.get_next_interval(len(detections), soc)
        logger.debug(
            "Detected %d | %.0fms | next in %.0fs | SoC=%s",
            len(detections), elapsed_ms, interval,
            f"{soc:.0f}%" if soc is not None else "N/A",
        )
        time.sleep(interval)

    camera.close()
    logger.info("Detection loop stopped")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="BUGSI Insect Detector — Classical CV for Raspberry Pi 5 + Arducam 64MP"
    )
    parser.add_argument("--config", "-c", help="Path to config JSON file")
    parser.add_argument("--single", "-s", action="store_true", help="Single capture and exit")
    parser.add_argument("--mock", action="store_true", help="Use mock camera (no hardware)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )

    config = load_config(args.config)

    camera: CameraInterface
    if args.mock:
        camera = MockCamera(config)
    else:
        camera = ArducamCapture(config)

    if args.single:
        run_single_capture(camera, config)
    else:
        run_loop(camera, config)


if __name__ == "__main__":
    main()
