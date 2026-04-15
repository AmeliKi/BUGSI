"""
BUGSI Event Camera Insect Detector -- Prophesee IMX636.

Real-time insect tracking directly on the sparse event stream.
Grid-based clustering with persistent ID tracking. Frame generation
is only used for the optional display window.

Usage:
    python event_detector.py                          # live camera, display on
    python event_detector.py --no-display              # headless
    python event_detector.py --record                  # also record video
    python event_detector.py -i recording.raw          # replay a .raw file
    python event_detector.py -c my_config.yaml         # custom config
    python event_detector.py --min-size 10 --max-size 300

Keys (when display is on):
    q / ESC  -- quit
    s        -- manual snapshot
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import time
from pathlib import Path

# Prophesee HAL plugin path -- must be set before importing metavision.
# Override with the MV_HAL_PLUGIN_PATH env var if your install differs.
if "MV_HAL_PLUGIN_PATH" not in os.environ:
    _default_hal = "/opt/prophesee/openeb/build/lib"
    if os.path.isdir(_default_hal):
        os.environ["MV_HAL_PLUGIN_PATH"] = _default_hal

import cv2
import numpy as np
import yaml

from metavision_core.event_io import EventsIterator
from metavision_sdk_core import BaseFrameGenerationAlgorithm
from metavision_hal import DeviceDiscovery

# Optional noise filters
try:
    from metavision_sdk_core import ActivityNoiseFilterAlgorithm
    _HAS_ACTIVITY = True
except ImportError:
    _HAS_ACTIVITY = False

try:
    from metavision_sdk_core import TrailFilterAlgorithm
    _HAS_TRAIL = True
except ImportError:
    _HAS_TRAIL = False

logger = logging.getLogger("bugsi-event-detector")

# ---------------------------------------------------------------------------
# Default configuration
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG_PATH = Path(__file__).parent / "config" / "event_defaults.yaml"

DEFAULT_CONFIG: dict = {
    "camera": {
        "biases": {},
    },
    "tracking": {
        "update_frequency": 200,
        "accumulation_time_us": 10000,
        "cell_width": 7,
        "cell_height": 7,
        "activation_threshold": 10,
        "min_size": 10,
        "max_size": 300,
        "max_match_distance": 50,
        "max_missed_frames": 5,
    },
    "noise_filter": {
        "activity_time_ths": 10000,
        "trail_ths": 0,
    },
    "alert": {
        "enabled": True,
        "cooldown_s": 2.0,
    },
    "output": {
        "snapshot_dir": "./snapshots",
        "recording_dir": "./recordings",
    },
}


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into *base*, returning a new dict."""
    result = base.copy()
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def load_config(path: str | Path | None = None) -> dict:
    """Load config from YAML, merging with built-in defaults."""
    config_path = Path(path) if path else _DEFAULT_CONFIG_PATH
    if config_path.exists():
        with open(config_path) as fh:
            user_cfg = yaml.safe_load(fh) or {}
        return _deep_merge(DEFAULT_CONFIG, user_cfg)
    save_config(DEFAULT_CONFIG, config_path)
    logger.info("Created default config at %s", config_path)
    return DEFAULT_CONFIG.copy()


def save_config(cfg: dict, path: str | Path) -> None:
    """Persist *cfg* to a YAML file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as fh:
        yaml.dump(cfg, fh, default_flow_style=False, sort_keys=False)


# ---------------------------------------------------------------------------
# Grid-cluster tracker (operates on the sparse event stream, not frames)
# ---------------------------------------------------------------------------

class GridClusterTracker:
    """Grid-based event clustering with frame-to-frame ID tracking.

    All detection runs on the raw event coordinates -- no image is built.

    Pipeline per time-slice:
      1. Quantise event (x, y) into grid cells (cell_width x cell_height).
      2. Count events per cell; discard cells below activation_threshold.
      3. Flood-fill connected active cells into clusters.
      4. Filter clusters by min_size / max_size.
      5. Match clusters to existing tracks by nearest centre.
      6. Create new track IDs for unmatched clusters, age out lost tracks.
    """

    def __init__(self, cfg: dict) -> None:
        trk = cfg["tracking"]
        self.cell_w: int = trk["cell_width"]
        self.cell_h: int = trk["cell_height"]
        self.act_ths: int = trk["activation_threshold"]
        self.min_size: int = trk["min_size"]
        self.max_size: int = trk["max_size"]
        self.max_dist: int = trk.get("max_match_distance", 50)
        self.max_missed: int = trk.get("max_missed_frames", 5)

        self._next_id: int = 1
        # Active tracks: id -> {"cx", "cy", "w", "h", "missed"}
        self._tracks: dict[int, dict] = {}

    def process_events(self, events: np.ndarray) -> list[dict]:
        """Cluster *events*, match to existing tracks, return track dicts."""
        boxes = self._cluster(events)
        return self._match_and_update(boxes)

    # -- clustering (sparse, no image) --------------------------------------

    def _cluster(
        self, events: np.ndarray,
    ) -> list[tuple[int, int, int, int]]:
        if events.size == 0:
            return []

        xs = events["x"].astype(np.int32)
        ys = events["y"].astype(np.int32)
        gx = xs // self.cell_w
        gy = ys // self.cell_h

        # Event count per grid cell
        keys = gx.astype(np.int64) * 100_000 + gy.astype(np.int64)
        _, inv, counts = np.unique(keys, return_inverse=True, return_counts=True)

        # Keep only cells above activation threshold
        active_mask = counts[inv] >= self.act_ths
        if not np.any(active_mask):
            return []

        active_keys = np.unique(
            gx[active_mask].astype(np.int64) * 100_000
            + gy[active_mask].astype(np.int64)
        )
        cell_set: set[int] = set(active_keys.tolist())

        # Flood-fill connected active cells
        visited: set[int] = set()
        clusters: list[list[int]] = []
        for seed in active_keys:
            si = int(seed)
            if si in visited:
                continue
            cluster: list[int] = []
            queue = [si]
            while queue:
                cur = queue.pop()
                if cur in visited:
                    continue
                visited.add(cur)
                cluster.append(cur)
                cg_x, cg_y = divmod(cur, 100_000)
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        nb = (cg_x + dx) * 100_000 + (cg_y + dy)
                        if nb in cell_set and nb not in visited:
                            queue.append(nb)
            clusters.append(cluster)

        # Convert cell clusters to pixel bounding boxes
        boxes: list[tuple[int, int, int, int]] = []
        for cluster in clusters:
            arr = np.array(cluster, dtype=np.int64)
            cell_xs, cell_ys = np.divmod(arr, 100_000)
            x0 = int(cell_xs.min()) * self.cell_w
            y0 = int(cell_ys.min()) * self.cell_h
            x1 = (int(cell_xs.max()) + 1) * self.cell_w
            y1 = (int(cell_ys.max()) + 1) * self.cell_h
            w, h = x1 - x0, y1 - y0
            size = max(w, h)
            if self.min_size <= size <= self.max_size:
                boxes.append((x0, y0, w, h))
        return boxes

    # -- ID tracking (nearest-neighbour matching) ---------------------------

    def _match_and_update(
        self, boxes: list[tuple[int, int, int, int]],
    ) -> list[dict]:
        det_centres = [
            (x + w // 2, y + h // 2, x, y, w, h) for x, y, w, h in boxes
        ]

        matched_tids: set[int] = set()
        matched_dets: set[int] = set()

        # Greedy nearest-neighbour
        pairs: list[tuple[float, int, int]] = []
        for tid, trk in self._tracks.items():
            for di, (cx, cy, *_) in enumerate(det_centres):
                dist = ((trk["cx"] - cx) ** 2 + (trk["cy"] - cy) ** 2) ** 0.5
                if dist <= self.max_dist:
                    pairs.append((dist, tid, di))
        pairs.sort()

        for _, tid, di in pairs:
            if tid in matched_tids or di in matched_dets:
                continue
            cx, cy, x, y, w, h = det_centres[di]
            self._tracks[tid].update(cx=cx, cy=cy, w=w, h=h, missed=0)
            matched_tids.add(tid)
            matched_dets.add(di)

        # New tracks for unmatched detections
        for di, (cx, cy, x, y, w, h) in enumerate(det_centres):
            if di in matched_dets:
                continue
            tid = self._next_id
            self._next_id += 1
            self._tracks[tid] = {"cx": cx, "cy": cy, "w": w, "h": h, "missed": 0}

        # Age out lost tracks
        lost: list[int] = []
        for tid in self._tracks:
            if tid not in matched_tids and tid not in {
                t for t in self._tracks
                if self._tracks[t]["missed"] == 0
                and tid >= self._next_id - len(det_centres)
            }:
                self._tracks[tid]["missed"] += 1
                if self._tracks[tid]["missed"] > self.max_missed:
                    lost.append(tid)
        for tid in lost:
            del self._tracks[tid]

        # Return only tracks that were seen this frame
        return [
            {
                "t": 0,
                "x": trk["cx"] - trk["w"] // 2,
                "y": trk["cy"] - trk["h"] // 2,
                "w": trk["w"],
                "h": trk["h"],
                "track_id": tid,
            }
            for tid, trk in self._tracks.items()
            if trk["missed"] == 0
        ]


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

class EventDetectorApp:
    """Main application: event stream -> track -> display / record / alert."""

    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.cfg = load_config(args.config)
        if args.min_size is not None:
            self.cfg["tracking"]["min_size"] = args.min_size
        if args.max_size is not None:
            self.cfg["tracking"]["max_size"] = args.max_size

        self.total_detections: int = 0
        self._known_ids: set[int] = set()
        self._last_alert: float = 0.0
        self._writer: cv2.VideoWriter | None = None

        Path(self.cfg["output"]["snapshot_dir"]).mkdir(parents=True, exist_ok=True)
        if args.record:
            Path(self.cfg["output"]["recording_dir"]).mkdir(parents=True, exist_ok=True)

    # -- camera / HAL -------------------------------------------------------

    @staticmethod
    def _open_device() -> object | None:
        try:
            device = DeviceDiscovery.open("")
            if device is None:
                logger.warning("DeviceDiscovery.open returned None -- no camera found")
            return device
        except Exception as exc:
            logger.warning("Could not open HAL device: %s", exc)
            return None

    def _apply_biases(self, device: object) -> None:
        biases_cfg: dict = self.cfg["camera"].get("biases", {})
        if not biases_cfg:
            return
        try:
            hw = device.get_i_ll_biases()  # type: ignore[union-attr]
        except Exception as exc:
            logger.warning("Cannot access bias interface: %s", exc)
            return
        for name, value in biases_cfg.items():
            try:
                hw.set(name, int(value))
                actual = hw.get(name)
                logger.info("Bias %-15s  set=%d  actual=%d", name, value, actual)
            except Exception as exc:
                logger.warning("Bias %s: %s", name, exc)

    # -- noise filters ------------------------------------------------------

    @staticmethod
    def _create_noise_filters(
        width: int, height: int, cfg: dict,
    ) -> tuple[object | None, object | None, object | None]:
        """Return ``(activity_filter, trail_filter, events_buf)``."""
        nf = cfg["noise_filter"]
        activity = None
        trail = None
        events_buf = None

        if nf["activity_time_ths"] > 0 and _HAS_ACTIVITY:
            try:
                activity = ActivityNoiseFilterAlgorithm(width, height, nf["activity_time_ths"])
                events_buf = activity.get_empty_output_buffer()
                logger.info("Activity noise filter enabled (ths=%d us)", nf["activity_time_ths"])
            except Exception as exc:
                logger.warning("ActivityNoiseFilter init failed: %s", exc)

        if nf["trail_ths"] > 0 and _HAS_TRAIL:
            try:
                trail = TrailFilterAlgorithm(width, height, nf["trail_ths"])
                if events_buf is None:
                    events_buf = trail.get_empty_output_buffer()
                logger.info("Trail filter enabled (ths=%d us)", nf["trail_ths"])
            except Exception as exc:
                logger.warning("TrailFilter init failed: %s", exc)

        return activity, trail, events_buf

    # -- snapshot / recording -----------------------------------------------

    def _save_snapshot(self, frame: np.ndarray, tracks: list[dict]) -> None:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        snap_dir = self.cfg["output"]["snapshot_dir"]
        img_path = os.path.join(snap_dir, f"det_{ts}.png")
        cv2.imwrite(img_path, frame)
        meta_path = os.path.join(snap_dir, f"det_{ts}.json")
        with open(meta_path, "w") as fh:
            json.dump(
                {
                    "timestamp": ts,
                    "total_detections": self.total_detections,
                    "tracks": tracks,
                },
                fh,
                indent=2,
            )
        logger.info("Snapshot saved: %s  (%d tracks)", img_path, len(tracks))

    def _start_recording(self, width: int, height: int, fps: float) -> None:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        rec_dir = self.cfg["output"]["recording_dir"]
        path = os.path.join(rec_dir, f"rec_{ts}.avi")
        fourcc = cv2.VideoWriter_fourcc(*"XVID")
        self._writer = cv2.VideoWriter(path, fourcc, fps, (width, height))
        logger.info("Recording -> %s  (%.1f fps)", path, fps)

    def _stop_recording(self) -> None:
        if self._writer is not None:
            self._writer.release()
            self._writer = None
            logger.info("Recording stopped")

    # -- drawing (only for display / recording, not detection) --------------

    @staticmethod
    def _draw_tracking_results(
        output_img: np.ndarray,
        track_dicts: list[dict],
        total: int,
        recording: bool,
    ) -> None:
        """Draw bounding boxes + IDs on *output_img* (in-place)."""
        for t in track_dicts:
            x, y, w, h = t["x"], t["y"], t["w"], t["h"]
            tid = t["track_id"]
            cv2.rectangle(output_img, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.putText(
                output_img, f"#{tid}  {w}x{h}", (x, y - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1,
            )
        status = f"Tracking: {len(track_dicts)}  Total: {total}"
        if recording:
            status += "  [REC]"
        cv2.putText(
            output_img, status, (8, 18),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 255), 1,
        )

    # -- alert logic --------------------------------------------------------

    def _alert_ready(self) -> bool:
        cooldown = self.cfg["alert"]["cooldown_s"]
        now = time.time()
        if now - self._last_alert >= cooldown:
            self._last_alert = now
            return True
        return False

    # -- main loop ----------------------------------------------------------

    def run(self) -> None:
        logger.info("IMX636 Event Insect Detector starting")
        trk_cfg = self.cfg["tracking"]
        alert_cfg = self.cfg["alert"]
        source: str = self.args.input or ""

        update_freq = trk_cfg["update_frequency"]
        delta_t = int(1_000_000 / update_freq)

        # -- Open HAL device for bias control (live camera only) --
        device = None
        if not self.args.input:
            device = self._open_device()
            if device is None:
                logger.error(
                    "No camera found. Check that the IMX636 is connected "
                    "and that you have permissions (e.g. udev rules). "
                    "Use -i <file.raw> to replay a recorded file instead."
                )
                return
            self._apply_biases(device)

        # -- Open event iterator --
        if device is not None:
            try:
                mv_iter = EventsIterator(device, delta_t=delta_t)
            except TypeError:
                logger.warning(
                    "EventsIterator rejected Device object; "
                    "opening camera via empty path (biases already applied)"
                )
                mv_iter = EventsIterator("", delta_t=delta_t)
        else:
            mv_iter = EventsIterator(source, delta_t=delta_t)

        height, width = mv_iter.get_size()
        logger.info("Sensor %dx%d  update=%dHz", width, height, update_freq)

        # -- Tracker (works on events, not images) --
        tracker = GridClusterTracker(self.cfg)
        logger.info(
            "Tracker: cell=%dx%d  activation=%d  size=%d-%d",
            trk_cfg["cell_width"], trk_cfg["cell_height"],
            trk_cfg["activation_threshold"],
            trk_cfg["min_size"], trk_cfg["max_size"],
        )

        # -- Noise filters --
        activity_filter, trail_filter, events_buf = self._create_noise_filters(
            width, height, self.cfg,
        )

        # -- Frame buffer (only allocated when display / recording is on) --
        show = not self.args.no_display
        need_frame = show or self.args.record
        output_img = np.zeros((height, width, 3), dtype=np.uint8) if need_frame else None

        if self.args.record:
            fps = min(float(update_freq), 60.0)
            self._start_recording(width, height, fps)

        try:
            for raw_events in mv_iter:
                if raw_events.size == 0:
                    continue

                # -- Noise filtering --
                if activity_filter is not None:
                    activity_filter.process_events(raw_events, events_buf)
                    if trail_filter is not None:
                        trail_filter.process_events_(events_buf)
                    evs = events_buf.numpy()
                elif trail_filter is not None:
                    trail_filter.process_events(raw_events, events_buf)
                    evs = events_buf.numpy()
                else:
                    evs = raw_events

                if evs.size == 0:
                    continue

                # -- Track on the event stream (no image involved) --
                track_dicts = tracker.process_events(evs)

                # -- Alert on new track IDs --
                if track_dicts and alert_cfg["enabled"]:
                    current_ids = {t["track_id"] for t in track_dicts}
                    new_ids = current_ids - self._known_ids
                    self._known_ids = current_ids

                    if new_ids and self._alert_ready():
                        self.total_detections += len(new_ids)
                        logger.info(
                            "DETECTED %d new object(s) (IDs: %s)  [total=%d]",
                            len(new_ids),
                            ", ".join(str(i) for i in sorted(new_ids)),
                            self.total_detections,
                        )
                        if need_frame:
                            BaseFrameGenerationAlgorithm.generate_frame(evs, output_img)
                            self._draw_tracking_results(
                                output_img, track_dicts,
                                self.total_detections,
                                self._writer is not None,
                            )
                            self._save_snapshot(output_img, track_dicts)
                else:
                    # Tracks disappeared -- clear known IDs so they can re-trigger
                    if not track_dicts:
                        self._known_ids.clear()

                # -- Visualise (only when display / recording is on) --
                if need_frame:
                    BaseFrameGenerationAlgorithm.generate_frame(evs, output_img)
                    self._draw_tracking_results(
                        output_img, track_dicts,
                        self.total_detections,
                        self._writer is not None,
                    )

                    if self._writer is not None:
                        self._writer.write(output_img)

                    if show:
                        cv2.imshow("IMX636 Insect Detector", output_img)
                        key = cv2.waitKey(1) & 0xFF
                        if key in (ord("q"), 27):
                            break
                        if key == ord("s"):
                            self._save_snapshot(output_img, track_dicts)

        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        finally:
            self._stop_recording()
            if show:
                cv2.destroyAllWindows()
            logger.info("Done -- %d total detections", self.total_detections)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="BUGSI Event Camera Insect Detector (Prophesee IMX636)",
    )
    p.add_argument(
        "-i", "--input", default=None,
        help="Input .raw / .dat file for replay (default: live camera)",
    )
    p.add_argument(
        "-c", "--config", default=None,
        help="YAML config file (default: config/event_defaults.yaml)",
    )
    p.add_argument(
        "--min-size", type=int, default=None,
        help="Min tracked object size in pixels (overrides config)",
    )
    p.add_argument(
        "--max-size", type=int, default=None,
        help="Max tracked object size in pixels (overrides config)",
    )
    p.add_argument(
        "--no-display", action="store_true",
        help="Run headless -- no OpenCV window",
    )
    p.add_argument(
        "--record", action="store_true",
        help="Record the visualisation as an AVI video",
    )
    p.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable debug-level logging",
    )
    return p


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    EventDetectorApp(args).run()


if __name__ == "__main__":
    main()
