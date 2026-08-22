from __future__ import annotations

import math
import struct
import unittest

from gyrofix.intervals import parse_time_rows
from gyrofix.processor import _merge_intervals, default_output_path, parse_time
from gyrofix.protobuf import ProtobufError, quaternion_refs, write_quaternion
from gyrofix.smoothing import dot, smooth_quaternions


def varint(value: int) -> bytes:
    output = bytearray()
    while value >= 0x80:
        output.append((value & 0x7F) | 0x80)
        value >>= 7
    output.append(value)
    return bytes(output)


def message(field_number: int, payload: bytes) -> bytes:
    return varint(field_number << 3 | 2) + varint(len(payload)) + payload


def quaternion(values: tuple[float, float, float, float]) -> bytes:
    output = bytearray()
    for field_number, value in enumerate(values, start=1):
        output += varint(field_number << 3 | 5)
        output += struct.pack("<f", value)
    return bytes(output)


class CoreTests(unittest.TestCase):
    def test_parse_time(self) -> None:
        self.assertEqual(parse_time("22.5"), 22.5)
        self.assertEqual(parse_time("00:00:22.500"), 22.5)
        self.assertEqual(parse_time("1:02.5"), 62.5)

    def test_parse_time_rejects_non_finite_and_invalid_clock_values(self) -> None:
        for value in ("nan", "inf", "1:60", "1:-1", math.inf, math.nan):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_time(value)

    def test_optional_time_rows_ignore_only_fully_blank_rows(self) -> None:
        self.assertEqual(
            parse_time_rows([("22", "24"), ("", ""), ("30.5", "31")]),
            [(1, 22.0, 24.0), (3, 30.5, 31.0)],
        )
        with self.assertRaisesRegex(ValueError, "2번"):
            parse_time_rows([("22", "24"), ("25", "")])
        with self.assertRaises(ValueError):
            parse_time_rows([("", "")])

    def test_time_validation_can_report_in_english(self) -> None:
        with self.assertRaisesRegex(ValueError, "Minutes and seconds"):
            parse_time("1:60", language="en")
        with self.assertRaisesRegex(ValueError, "Range 2"):
            parse_time_rows(
                [("22", "24"), ("25", "")],
                language="en",
            )

    def test_interval_merge_rejects_non_finite_values(self) -> None:
        for interval in ((0.0, math.inf), (math.nan, 1.0)):
            with self.subTest(interval=interval), self.assertRaises(ValueError):
                _merge_intervals([interval])

    def test_default_output_path_keeps_extension_case(self) -> None:
        self.assertEqual(
            default_output_path("clip.MP4").name,
            "clip_gyro_fixed.MP4",
        )

    def test_wm169_quaternion_patch_keeps_message_size(self) -> None:
        raw_quaternion = quaternion((0.5, -0.5, -0.5, 0.5))
        product = message(3, message(3, message(2, message(3, raw_quaternion))))
        data = bytearray(product)
        refs = quaternion_refs(data, "wm169")
        self.assertEqual(len(refs), 1)
        before = len(data)
        replacement = [0.6, -0.4, -0.4, math.sqrt(0.48)]
        write_quaternion(data, refs[0], replacement)
        self.assertEqual(len(data), before)
        updated = quaternion_refs(data, "wm169")[0].values
        for actual, expected in zip(updated, replacement):
            self.assertAlmostEqual(actual, expected, places=6)

    def test_quaternion_patch_rejects_invalid_component_count(self) -> None:
        raw_quaternion = quaternion((0.5, -0.5, -0.5, 0.5))
        product = message(3, message(3, message(2, message(3, raw_quaternion))))
        ref = quaternion_refs(product, "wm169")[0]
        with self.assertRaises(ProtobufError):
            write_quaternion(bytearray(product), ref, [1.0, 0.0, 0.0])

    def test_local_smoothing_reduces_bump_and_preserves_outside(self) -> None:
        rate = 200
        times = [index / rate for index in range(rate * 4 + 1)]
        values = []
        for time in times:
            angle = 0.2 * time
            if 1.8 < time < 2.2:
                angle += 0.15 * math.sin((time - 1.8) / 0.4 * math.pi)
            values.append([math.cos(angle / 2), 0.0, math.sin(angle / 2), 0.0])
        output = smooth_quaternions(times, values, 1.0, 3.0, smoothing_ms=180)
        self.assertEqual(output[0], values[0])
        self.assertEqual(output[-1], values[-1])
        middle = rate * 2
        expected_angle = 0.2 * 2.0
        expected = [math.cos(expected_angle / 2), 0.0, math.sin(expected_angle / 2), 0.0]
        self.assertGreater(dot(output[middle], expected), dot(values[middle], expected))

    def test_smoothing_rejects_non_finite_settings(self) -> None:
        times = [0.0, 1.0]
        quaternions = [[1.0, 0.0, 0.0, 0.0]] * 2
        with self.assertRaises(ValueError):
            smooth_quaternions(times, quaternions, 0.0, 1.0, smoothing_ms=math.inf)
        with self.assertRaises(ValueError):
            smooth_quaternions(times, quaternions, 0.0, 1.0, strength=math.nan)


if __name__ == "__main__":
    unittest.main()
