from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gyrofix.detection import describe_detection, detect_video_jitter


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("--start", type=float, default=22.0)
    parser.add_argument("--end", type=float, default=24.0)
    args = parser.parse_args()
    result = detect_video_jitter(args.video, args.start, args.end)
    print(describe_detection(result))
    print()
    print(
        f"samples={result.sample_count}, rate={result.sample_rate:.1f}Hz, "
        f"baseline={result.baseline_metric:.3f}, threshold={result.threshold_metric:.3f}"
    )


if __name__ == "__main__":
    main()
