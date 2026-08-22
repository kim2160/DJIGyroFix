from __future__ import annotations

import argparse
from pathlib import Path

from .processor import default_output_path, parse_time, process_video


def main() -> None:
    parser = argparse.ArgumentParser(description="Smooth a selected DJI gyro interval without re-encoding video.")
    parser.add_argument("video", type=Path)
    parser.add_argument("start", help="Start time, e.g. 22 or 00:00:22.0")
    parser.add_argument("end", help="End time, e.g. 24 or 00:00:24.0")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--smoothing-ms", type=float, default=180.0)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    output = args.output or default_output_path(args.video)

    def progress(stage: str, amount: float) -> None:
        print(f"\r{stage}: {amount * 100:5.1f}%", end="", flush=True)

    result = process_video(
        args.video,
        output,
        parse_time(args.start),
        parse_time(args.end),
        smoothing_ms=args.smoothing_ms,
        overwrite=args.overwrite,
        progress=progress,
    )
    print()
    print(f"Saved: {result.output_path}")
    print(f"Changed quaternions: {result.quaternions_changed:,}")
    print(f"High-frequency reduction: {result.improvement_percent:.1f}%")


if __name__ == "__main__":
    main()
