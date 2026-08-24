# DJI Gyro Fix v0.92

DJI Gyro Fix is an offline desktop tool for Windows and macOS that smooths
attitude (quaternion) metadata in selected time ranges of original DJI MP4/MOV
files. It does not re-encode video or audio. The original file is preserved and
the repaired copy is saved with `_gyro_fixed` appended to its name.

> This project is beta software. Keep a separate backup of important footage
> and test it on a copy of the original camera file first.

## Downloads

### macOS

- [DJI Gyro Fix v0.92 for macOS (Apple Silicon and Intel)](https://github.com/kim2160/DJIGyroFix/releases/download/v0.92/DJI_Gyro_Fix_v0.92_macOS_universal2.zip)
- [SHA-256 checksums](https://github.com/kim2160/DJIGyroFix/releases/download/v0.92/SHA256SUMS.txt)

The macOS app is signed with an Apple Developer ID and notarized by Apple.

### Windows

- [DJI Gyro Fix v0.91 for Windows](https://github.com/kim2160/DJIGyroFix/releases/download/v0.91/DJI_Gyro_Fix.exe)
- [View all releases and release notes](https://github.com/kim2160/DJIGyroFix/releases)

The Windows executable is not currently code-signed, so Windows SmartScreen
may display a warning. You can compare the downloaded file with the SHA-256
checksum published in the release notes.

## Features

- Runs fully offline without an internet connection, AI service, or Gyroflow
- English UI by default, with `KOR` and `ENG` language buttons beside the title
- Processes up to 10 start/end time ranges in one operation
- Ignores completely blank time rows and automatically merges overlapping ranges
- Detects abnormal high-frequency attitude jitter in selected ranges
- Provides Weak, Medium, Strong, and Very Strong smoothing presets
- Modifies only DJI quaternion fields without re-encoding video or audio tracks
- Uses unique temporary files and atomic replacement to avoid incomplete outputs

## How it protects the original file

The app first copies the complete original file to a separate temporary file.
It then writes only the quaternion float fields of the relevant `djmd` samples
at their original byte positions. File size and MP4 track layout remain
unchanged, and only a fully written file is moved to the final output path.

You need at least as much free disk space as the original file. The app cannot
be closed during processing until the output has been saved safely.

## Usage

1. Download the package for your operating system from GitHub Releases.
2. On macOS, extract the ZIP and open `DJI Gyro Fix.app`. On Windows, run
   `DJI_Gyro_Fix.exe`.
3. Use the `KOR` or `ENG` button beside the title if you want to change the UI
   language.
4. Click `Browse` and select an original DJI MP4/MOV camera file.
5. Enter the start and end time of the range to process.
6. Add more ranges with `+` if needed. Up to 10 ranges can be entered.
7. Click `DETECT` to inspect possible jitter, or click `FIX` to process the
   selected ranges immediately.
8. Find the repaired file named `original_name_gyro_fixed.MP4` beside the
   original.

Supported time formats:

- `22`
- `22.5`
- `00:00:22.500`
- `1:02.5`

Additional rows with both start and end fields blank are skipped. A row with
only one field filled is reported as an error.

## Jitter detection

The detector calculates angular velocity from quaternion samples and compares
high-frequency residuals at roughly 10 ms intervals with the normal level of
the selected range. Nearby spikes are grouped into a single event. Each event
reports:

- Start, end, and peak time
- A `0–10` strength score and Weak/Medium/Strong severity
- The primary X/Y/Z rotation axis
- Magnitude relative to the baseline and the number of rapid changes

Detection is an advisory feature. `FIX` processes every valid user-entered
range whether or not jitter was detected.

## Supported files and limitations

The following DJI protobuf quaternion structures are currently supported:

- `wm169`
- `wa530`
- `oq101`

The following files are not supported:

- Edited files without `djmd` attitude metadata
- Fragmented MP4 files and other container layouts not supported by the parser
- Encrypted or unknown DJI metadata variants
- Files produced by manufacturers other than DJI

Support is determined from the actual MP4 tracks and metadata, not only from
the filename extension.

## Development

Requirements:

- Python 3.12 or later
- No external runtime dependencies
- Desktop UI validated on Windows and macOS

Run the desktop app:

```text
python app.py
```

Process a single range from the command line:

```text
python -m gyrofix.cli "video.MP4" 22 24
```

## Tests

```text
python -m compileall -q app.py gyrofix tests tools
python -m unittest discover -s tests -v
```

The test suite covers time parsing, optional rows, interval merging, protobuf
field writes, quaternion smoothing, jitter event grouping, MP4 table
validation, atomic output, and temporary-file cleanup after failures.

## Windows executable build

```powershell
.\build_exe.bat
```

The output is created at `dist/DJI_Gyro_Fix.exe`. The `dist/` directory is
excluded from the source repository. Public binaries should be distributed
through GitHub Releases or the provided manual build workflow artifacts.

## Project structure

```text
gyrofix/             Core MP4, protobuf, detection, smoothing, and UI code
tests/               Regression tests
tools/               Sample inspection and output byte-verification tools
docs/                End-user documentation
packaging/           Windows and macOS packaging metadata and assets
.github/workflows/   Cross-platform tests and manual Windows builds
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines and
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for information about related
open-source work.

## License

Copyright (C) 2026 dronefriends.kr

This project is distributed under the
[GNU General Public License v3.0 only](LICENSE). If you distribute a modified
version of the program, you must also distribute the corresponding source code
under GPL v3.0. See `LICENSE` for the full terms.
