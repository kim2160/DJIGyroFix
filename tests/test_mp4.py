from __future__ import annotations

from io import BytesIO
import struct
import unittest

from gyrofix.mp4 import Mp4Error, Track, iter_boxes


class Mp4Tests(unittest.TestCase):
    def test_track_finalization_maps_samples_and_timestamps(self) -> None:
        track = Track(
            track_id=7,
            timescale=100,
            duration=30,
            sample_sizes=[2, 3, 4],
            chunk_offsets=[100, 200],
            stsc=[(1, 2, 1), (2, 1, 1)],
            stts=[(3, 10)],
        )
        track.finalize()
        self.assertEqual(track.sample_offsets, [100, 102, 200])
        self.assertEqual(track.sample_dts, [0, 10, 20])

    def test_track_rejects_invalid_chunk_table(self) -> None:
        track = Track(
            track_id=7,
            timescale=100,
            sample_sizes=[4],
            chunk_offsets=[100],
            stsc=[(2, 1, 1)],
            stts=[(1, 10)],
        )
        with self.assertRaises(Mp4Error):
            track.finalize()

    def test_box_iterator_rejects_box_beyond_parent_boundary(self) -> None:
        data = struct.pack(">I4s", 128, b"free") + b"payload"
        with self.assertRaises(Mp4Error):
            list(iter_boxes(BytesIO(data), 0, len(data)))


if __name__ == "__main__":
    unittest.main()
