"""Tests for the adaptive capture scheduler."""

from __future__ import annotations

from detector import AdaptiveScheduler


class TestAdaptiveScheduler:
    """Tests for time-of-day and activity-based interval adjustment."""

    def test_night_hours_detected(self, default_config: dict) -> None:
        scheduler = AdaptiveScheduler(default_config)
        assert scheduler.is_night(hour=23) is True
        assert scheduler.is_night(hour=3) is True

    def test_day_hours_not_night(self, default_config: dict) -> None:
        scheduler = AdaptiveScheduler(default_config)
        assert scheduler.is_night(hour=12) is False
        assert scheduler.is_night(hour=8) is False

    def test_peak_hours_detected(self, default_config: dict) -> None:
        scheduler = AdaptiveScheduler(default_config)
        assert scheduler.is_peak(hour=10) is True
        assert scheduler.is_peak(hour=15) is True

    def test_off_peak_hours(self, default_config: dict) -> None:
        scheduler = AdaptiveScheduler(default_config)
        assert scheduler.is_peak(hour=7) is False
        assert scheduler.is_peak(hour=20) is False

    def test_detections_decrease_interval(self, default_config: dict) -> None:
        scheduler = AdaptiveScheduler(default_config)
        interval_with = scheduler.get_next_interval(detection_count=3)
        # Reset
        scheduler._consecutive_empty = 0
        interval_without = scheduler.get_next_interval(detection_count=0)
        assert interval_with < interval_without

    def test_no_detections_increase_interval(self, default_config: dict) -> None:
        scheduler = AdaptiveScheduler(default_config)
        intervals = []
        for _ in range(5):
            intervals.append(scheduler.get_next_interval(detection_count=0))
        # Each successive empty capture should increase interval
        for i in range(1, len(intervals)):
            assert intervals[i] >= intervals[i - 1]

    def test_interval_clamped_to_min(self, default_config: dict) -> None:
        scheduler = AdaptiveScheduler(default_config)
        interval = scheduler.get_next_interval(detection_count=10)
        assert interval >= default_config["scheduling"]["min_interval_seconds"]

    def test_interval_clamped_to_max(self, default_config: dict) -> None:
        scheduler = AdaptiveScheduler(default_config)
        # Simulate many empty captures to push interval up
        for _ in range(20):
            scheduler.get_next_interval(detection_count=0)
        interval = scheduler.get_next_interval(detection_count=0)
        assert interval <= default_config["scheduling"]["max_interval_seconds"]

    def test_low_battery_increases_interval(self, default_config: dict) -> None:
        scheduler = AdaptiveScheduler(default_config)
        normal = scheduler.get_next_interval(detection_count=1, battery_soc=80.0)
        scheduler._consecutive_empty = 0
        low_bat = scheduler.get_next_interval(detection_count=1, battery_soc=10.0)
        assert low_bat > normal

    def test_should_shutdown_at_critical_battery(self, default_config: dict) -> None:
        scheduler = AdaptiveScheduler(default_config)
        assert scheduler.should_shutdown(battery_soc=3.0, threshold=5.0) is True
        assert scheduler.should_shutdown(battery_soc=10.0, threshold=5.0) is False

    def test_non_adaptive_returns_base_interval(self, default_config: dict) -> None:
        config = dict(default_config)
        config["scheduling"] = dict(config["scheduling"])
        config["scheduling"]["adaptive"] = False
        scheduler = AdaptiveScheduler(config)
        interval = scheduler.get_next_interval(detection_count=0)
        assert interval == config["scheduling"]["capture_interval_seconds"]
