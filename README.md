# DJI Gyro Fix v0.92

DJI Gyro Fix is an offline desktop tool that smooths attitude (quaternion)
metadata in selected time ranges of original DJI MP4/MOV files. It does not
re-encode video or audio, and it never modifies the original file.

> This is beta software. Back up important footage and test on a copy first.

## Downloads

- [macOS v0.92 — Apple Silicon and Intel](https://github.com/kim2160/DJIGyroFix/releases/download/v0.92/DJI_Gyro_Fix_v0.92_macOS_universal2.zip)
- [Windows v0.91](https://github.com/kim2160/DJIGyroFix/releases/download/v0.91/DJI_Gyro_Fix.exe)
- [All releases and checksums](https://github.com/kim2160/DJIGyroFix/releases)

The macOS app is signed with an Apple Developer ID and notarized by Apple. The
Windows executable is not currently code-signed and may trigger SmartScreen.

## When to use it with Gyroflow

Gyroflow stabilization can sometimes make a brief gyro spike look more abrupt
than it does in the original camera footage. If a section becomes more jittery
or jumps more strongly after stabilization:

1. Note the start and end time of the affected section in Gyroflow.
2. Process only that time range with DJI Gyro Fix.
3. Open the generated `_gyro_fixed` copy in Gyroflow and stabilize it again.

DJI Gyro Fix changes only the selected embedded gyro metadata. It does not
alter the image or audio tracks.

## Features

- English and Korean UI
- Up to 10 time ranges per operation
- Abnormal high-frequency attitude-jitter detection
- Four smoothing strengths
- No video or audio re-encoding
- Original-file preservation and atomic output saving
- Fully offline operation

## Usage

1. Open `DJI Gyro Fix.app` on macOS or `DJI_Gyro_Fix.exe` on Windows.
2. Click `Browse` and select an original DJI MP4/MOV camera file.
3. Enter the start and end time of the affected range.
4. Add more ranges with `+` if needed.
5. Click `DETECT` to inspect possible jitter, or click `FIX` directly.
6. Use the generated `original_name_gyro_fixed.MP4` file.

Supported time formats include `22`, `22.5`, `00:00:22.500`, and `1:02.5`.
Completely blank rows are ignored, and overlapping ranges are merged.

## Compatibility

Supported DJI protobuf structures: `wm169`, `wa530`, and `oq101`.

Edited files without `djmd` attitude metadata, fragmented MP4 containers,
encrypted or unknown DJI metadata, and non-DJI files are not supported.
Compatibility is determined from the actual metadata, not the file extension.

## Development

Requires Python 3.12 or later and has no external runtime dependencies.

```text
python app.py
python -m unittest discover -s tests -v
```

See [CONTRIBUTING.md](CONTRIBUTING.md) and
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for development and attribution
details.

## License

Copyright (C) 2026 dronefriends.kr

Distributed under the [GNU General Public License v3.0 only](LICENSE).
