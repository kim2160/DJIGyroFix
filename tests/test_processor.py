from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from gyrofix.mp4 import Track
from gyrofix.processor import process_video_intervals


class ProcessorTests(unittest.TestCase):
    @staticmethod
    def _metadata() -> Track:
        return Track(
            track_id=1,
            timescale=1,
            duration=10,
            sample_sizes=[4],
            sample_offsets=[4],
            sample_dts=[0],
        )

    @staticmethod
    def _prepare_with_patch(*args: object, **_kwargs: object) -> tuple[int, int, float, float]:
        patches = args[7]
        if not isinstance(patches, dict):
            raise TypeError("expected patch dictionary")
        patches[0] = b"WXYZ"
        return 1, 1, 10.0, 1.0

    def test_processing_writes_atomically_and_cleans_temporary_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.MP4"
            output = root / "output.MP4"
            source.write_bytes(b"0000abcd1111")

            with (
                patch(
                    "gyrofix.processor.inspect_video",
                    return_value=([], self._metadata(), "wm169"),
                ),
                patch(
                    "gyrofix.processor._prepare_interval",
                    side_effect=self._prepare_with_patch,
                ),
            ):
                result = process_video_intervals(source, output, [(1.0, 2.0)])

            self.assertEqual(output.read_bytes(), b"0000WXYZ1111")
            self.assertEqual(result.output_path, output.resolve())
            self.assertEqual(list(root.glob("*.partial")), [])
            self.assertEqual(list(root.glob(".*.partial")), [])

    def test_copy_failure_removes_partial_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.MP4"
            output = root / "output.MP4"
            source.write_bytes(b"0000abcd1111")

            with (
                patch(
                    "gyrofix.processor.inspect_video",
                    return_value=([], self._metadata(), "wm169"),
                ),
                patch(
                    "gyrofix.processor._prepare_interval",
                    side_effect=self._prepare_with_patch,
                ),
                patch(
                    "gyrofix.processor._copy_with_progress",
                    side_effect=OSError("copy failed"),
                ),
                self.assertRaisesRegex(OSError, "copy failed"),
            ):
                process_video_intervals(source, output, [(1.0, 2.0)])

            self.assertFalse(output.exists())
            self.assertEqual(list(root.glob(".*.partial")), [])


if __name__ == "__main__":
    unittest.main()
