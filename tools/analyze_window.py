from __future__ import annotations

import argparse
import math
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gyrofix.mp4 import find_dji_metadata_track, parse_tracks
from gyrofix.protobuf import detect_dji_variant, quaternion_refs


def dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def normalize(q: list[float]) -> list[float]:
    norm = math.sqrt(dot(q, q))
    return [value / norm for value in q]


def angle(a: list[float], b: list[float]) -> float:
    return 2.0 * math.acos(min(1.0, max(-1.0, abs(dot(a, b)))))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("--start", type=float, default=21.5)
    parser.add_argument("--end", type=float, default=24.5)
    args = parser.parse_args()

    metadata = find_dji_metadata_track(parse_tracks(args.video))
    points: list[tuple[float, list[float]]] = []
    with args.video.open("rb") as file:
        probes = []
        for index in range(min(5, len(metadata.sample_offsets))):
            file.seek(metadata.sample_offsets[index])
            probes.append(file.read(metadata.sample_sizes[index]))
        variant = detect_dji_variant(probes)

        indices = list(metadata.sample_range(args.start, args.end))
        for index in indices:
            file.seek(metadata.sample_offsets[index])
            data = file.read(metadata.sample_sizes[index])
            refs = quaternion_refs(data, variant)
            t0 = metadata.sample_dts[index] / metadata.timescale
            if index + 1 < len(metadata.sample_dts):
                t1 = metadata.sample_dts[index + 1] / metadata.timescale
            else:
                t1 = t0 + 0.01
            for subindex, ref in enumerate(refs):
                time = t0 + (t1 - t0) * subindex / max(1, len(refs))
                if args.start <= time <= args.end:
                    q = normalize(ref.values)
                    if points and dot(points[-1][1], q) < 0:
                        q = [-value for value in q]
                    points.append((time, q))

    velocity: list[tuple[float, float]] = []
    for (t0, q0), (t1, q1) in zip(points, points[1:]):
        dt = t1 - t0
        if dt > 0:
            velocity.append((t1, math.degrees(angle(q0, q1)) / dt))
    acceleration: list[tuple[float, float]] = []
    for (t0, v0), (t1, v1) in zip(velocity, velocity[1:]):
        dt = t1 - t0
        if dt > 0:
            acceleration.append((t1, abs(v1 - v0) / dt))

    values = [value for _, value in acceleration]
    print(f"variant={variant}, points={len(points)}, sample_rate~{len(points)/(args.end-args.start):.1f} Hz")
    print(
        "angular acceleration: "
        f"median={statistics.median(values):.2f}, "
        f"p99={sorted(values)[int(len(values) * 0.99)]:.2f}, "
        f"max={max(values):.2f} deg/s²"
    )
    print("largest events:")
    selected: list[tuple[float, float]] = []
    for time, value in sorted(acceleration, key=lambda item: item[1], reverse=True):
        if all(abs(time - existing_time) > 0.03 for existing_time, _ in selected):
            selected.append((time, value))
        if len(selected) == 15:
            break
    for time, value in sorted(selected):
        print(f"  {time:9.4f}s  {value:12.2f} deg/s²")

    print("quaternion snapshots (100 ms):")
    next_time = math.ceil(args.start * 10.0) / 10.0
    point_index = 0
    while next_time <= args.end + 1e-9:
        while point_index + 1 < len(points) and points[point_index + 1][0] <= next_time:
            point_index += 1
        time, q = points[point_index]
        print(f"  {time:7.3f}  " + " ".join(f"{value:+.7f}" for value in q))
        next_time += 0.1


if __name__ == "__main__":
    main()
