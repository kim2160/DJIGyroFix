from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from gyrofix.detection import (
    DetectionResult,
    _detect_events,
    describe_detection,
    detect_video_jitter,
)
from gyrofix.processor import _merge_intervals


class DetectionTests(unittest.TestCase):
    def test_detection_rejects_non_finite_and_negative_ranges(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.MP4"
            source.write_bytes(b"not-an-mp4")

            invalid_ranges = [
                (-1.0, 1.0),
                (0.0, float("nan")),
                (0.0, float("inf")),
            ]
            for start, end in invalid_ranges:
                with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                    detect_video_jitter(source, start, end)

    def test_nearby_spikes_are_reported_as_one_event(self) -> None:
        bin_seconds = 0.01
        start = 22.0
        count = 200
        times = [start + (index + 0.5) * bin_seconds for index in range(count)]
        metrics = [20.0] * count
        for index in range(85, 116):
            metrics[index] = 120.0 + (index % 5) * 20.0
        for index in range(128, 140):
            metrics[index] = 110.0
        energy = [[metric, metric * 3.0, metric * 0.1] for metric in metrics]
        events = _detect_events(
            times,
            metrics,
            energy,
            baseline=20.0,
            threshold=60.0,
            start_seconds=start,
            end_seconds=24.0,
            bin_seconds=bin_seconds,
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].dominant_axes, ("Y",))
        self.assertLess(events[0].start_seconds, 22.86)
        self.assertGreater(events[0].end_seconds, 23.39)

    def test_description_contains_range_peak_and_strength(self) -> None:
        times = [22.005 + index * 0.01 for index in range(200)]
        metrics = [20.0] * 200
        for index in range(90, 110):
            metrics[index] = 180.0
        energy = [[metric, metric * 2.0, 0.0] for metric in metrics]
        event = _detect_events(times, metrics, energy, 20.0, 60.0, 22.0, 24.0, 0.01)[0]
        result = DetectionResult(
            source_path=__import__("pathlib").Path("sample.mp4"),
            start_seconds=22.0,
            end_seconds=24.0,
            sample_count=4000,
            sample_rate=2000.0,
            baseline_metric=20.0,
            threshold_metric=60.0,
            events=(event,),
        )
        description = describe_detection(result)
        self.assertIn("이상 흔들림 1개", description)
        self.assertIn("최대 지점", description)
        self.assertIn("강도", description)
        self.assertIn("영향 축", description)

        english = describe_detection(result, language="en")
        self.assertIn("Detected 1 jitter event", english)
        self.assertIn("Peak", english)
        self.assertIn("Severity", english)
        self.assertIn("Axis", english)

    def test_overlapping_processing_intervals_are_merged(self) -> None:
        self.assertEqual(
            _merge_intervals([(3.0, 4.0), (1.0, 2.0), (1.5, 2.5)]),
            [(1.0, 2.5), (3.0, 4.0)],
        )


if __name__ == "__main__":
    unittest.main()
