from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gyrofix.processor import inspect_video
from gyrofix.protobuf import quaternion_refs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--start", type=float, default=22.0)
    parser.add_argument("--end", type=float, default=24.0)
    args = parser.parse_args()

    source_tracks, metadata, variant = inspect_video(args.source)
    output_tracks, output_metadata, output_variant = inspect_video(args.output)
    if args.source.stat().st_size != args.output.stat().st_size:
        raise RuntimeError("File sizes differ")

    track_signature = lambda tracks: [
        (
            track.track_id,
            track.handler_type,
            track.handler_name,
            track.sample_entry,
            track.timescale,
            track.duration,
            len(track.sample_sizes),
        )
        for track in tracks
    ]
    if track_signature(source_tracks) != track_signature(output_tracks):
        raise RuntimeError("MP4 track layouts differ")
    if variant != output_variant:
        raise RuntimeError("DJI metadata variants differ")

    allowed_offsets: set[int] = set()
    with args.source.open("rb") as file:
        for sample_index in metadata.sample_range(args.start, args.end):
            file.seek(metadata.sample_offsets[sample_index])
            data = file.read(metadata.sample_sizes[sample_index])
            refs = quaternion_refs(data, variant)
            sample_time = metadata.sample_dts[sample_index] / metadata.timescale
            if sample_index + 1 < len(metadata.sample_dts):
                next_time = metadata.sample_dts[sample_index + 1] / metadata.timescale
            else:
                next_time = metadata.duration_seconds
            for subindex, ref in enumerate(refs):
                time = sample_time + (next_time - sample_time) * subindex / max(1, len(refs))
                if args.start < time < args.end:
                    for component_offset in ref.offsets:
                        if component_offset is not None:
                            absolute = metadata.sample_offsets[sample_index] + component_offset
                            allowed_offsets.update(range(absolute, absolute + 4))

    changed = 0
    unexpected: list[int] = []
    first_changed = None
    last_changed = None
    position = 0
    chunk_size = 16 * 1024 * 1024
    with args.source.open("rb", buffering=0) as left, args.output.open("rb", buffering=0) as right:
        while True:
            left_data = left.read(chunk_size)
            right_data = right.read(chunk_size)
            if not left_data and not right_data:
                break
            if left_data != right_data:
                for index, (left_byte, right_byte) in enumerate(zip(left_data, right_data)):
                    if left_byte == right_byte:
                        continue
                    absolute = position + index
                    changed += 1
                    first_changed = absolute if first_changed is None else first_changed
                    last_changed = absolute
                    if absolute not in allowed_offsets and len(unexpected) < 20:
                        unexpected.append(absolute)
            position += len(left_data)

    result = {
        "same_size": True,
        "same_track_layout": True,
        "source_size": args.source.stat().st_size,
        "variant": variant,
        "changed_bytes": changed,
        "allowed_byte_positions": len(allowed_offsets),
        "unexpected_changes": unexpected,
        "first_changed_offset": first_changed,
        "last_changed_offset": last_changed,
        "output_metadata_samples": len(output_metadata.sample_sizes),
    }
    print(json.dumps(result, indent=2))
    if changed == 0 or unexpected:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
