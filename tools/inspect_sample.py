from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gyrofix.mp4 import find_dji_metadata_track, parse_tracks
from gyrofix.protobuf import detect_dji_variant, quaternion_refs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("--start", type=float, default=22.0)
    parser.add_argument("--end", type=float, default=24.0)
    args = parser.parse_args()

    tracks = parse_tracks(args.video)
    metadata = find_dji_metadata_track(tracks)
    with args.video.open("rb") as file:
        first_samples = []
        for index in range(min(5, len(metadata.sample_offsets))):
            file.seek(metadata.sample_offsets[index])
            first_samples.append(file.read(metadata.sample_sizes[index]))
        variant = detect_dji_variant(first_samples)

        result = {
            "tracks": [
                {
                    "id": track.track_id,
                    "handler": track.handler_type,
                    "name": track.handler_name,
                    "entry": track.sample_entry,
                    "timescale": track.timescale,
                    "duration": track.duration_seconds,
                    "samples": len(track.sample_sizes),
                }
                for track in tracks
            ],
            "dji_variant": variant,
            "window": [args.start, args.end],
            "window_samples": [],
            "quaternion_count": 0,
        }
        total = 0
        for index in metadata.sample_range(args.start, args.end):
            file.seek(metadata.sample_offsets[index])
            data = file.read(metadata.sample_sizes[index])
            count = len(quaternion_refs(data, variant))
            total += count
            if count:
                result["window_samples"].append(
                    {
                        "index": index,
                        "time": metadata.sample_dts[index] / metadata.timescale,
                        "size": metadata.sample_sizes[index],
                        "quaternions": count,
                    }
                )
        result["quaternion_count"] = total

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
