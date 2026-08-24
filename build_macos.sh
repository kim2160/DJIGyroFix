#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
APP_VERSION="$("$PYTHON_BIN" -c 'import sys, tomllib; print(tomllib.load(open(sys.argv[1], "rb"))["project"]["version"])' "$PROJECT_ROOT/pyproject.toml")"
TARGET_ARCH="${DJI_GYRO_FIX_ARCH:-$("$PYTHON_BIN" -c 'import platform; print(platform.machine())')}"
DIST_DIR="$PROJECT_ROOT/dist-macos"
BUILD_DIR="$PROJECT_ROOT/build-macos"
RELEASE_DIR="$DIST_DIR/release"
APP_PATH="$DIST_DIR/DJI Gyro Fix.app"
ARCHIVE_PATH="$RELEASE_DIR/DJI_Gyro_Fix_v${APP_VERSION}_macOS_${TARGET_ARCH}.zip"
PYINSTALLER_CONFIG_DIR="${PYINSTALLER_CONFIG_DIR:-${TMPDIR:-/tmp}/djigyrofix-pyinstaller}"
CODESIGN_IDENTITY="${DJI_GYRO_FIX_CODESIGN_IDENTITY:-}"
NOTARY_PROFILE="${DJI_GYRO_FIX_NOTARY_PROFILE:-djigyrofix-notary}"

# A relocatable python.org framework needs explicit Tcl/Tk library paths. A
# normal framework installation already resolves these paths without help.
PYTHON_BASE_PREFIX="$("$PYTHON_BIN" -c 'import sys; print(sys.base_prefix)')"
if [[ -z "${TCL_LIBRARY:-}" && -f "$PYTHON_BASE_PREFIX/lib/tcl8.6/init.tcl" ]]; then
  export TCL_LIBRARY="$PYTHON_BASE_PREFIX/lib/tcl8.6"
fi
if [[ -z "${TK_LIBRARY:-}" && -f "$PYTHON_BASE_PREFIX/lib/tk8.6/tk.tcl" ]]; then
  export TK_LIBRARY="$PYTHON_BASE_PREFIX/lib/tk8.6"
fi

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "macOS builds must run on macOS." >&2
  exit 1
fi

"$PYTHON_BIN" -c 'import PyInstaller, tkinter; from PIL import Image; assert tuple(map(int, PyInstaller.__version__.split("."))) >= (6, 22, 2); assert tkinter.TclVersion == 8.6 and tkinter.TkVersion == 8.6, "macOS release builds require Tcl/Tk 8.6 for Windows UI parity"; interpreter = tkinter.Tcl(); assert interpreter.eval("info patchlevel").startswith("8.6."), "Tcl/Tk 8.6 runtime resources are unavailable"'

if [[ -z "$CODESIGN_IDENTITY" ]]; then
  CODESIGN_IDENTITY="$(
    security find-identity -v -p codesigning \
      | sed -n 's/.*"\(Developer ID Application:.*\)"/\1/p'
  )"
fi
if [[ -z "$CODESIGN_IDENTITY" ]]; then
  echo "A Developer ID Application certificate with its private key is required." >&2
  exit 1
fi
if [[ "$CODESIGN_IDENTITY" == *$'\n'* ]]; then
  echo "Multiple Developer ID Application certificates were found." >&2
  echo "Set DJI_GYRO_FIX_CODESIGN_IDENTITY to the certificate to use." >&2
  exit 1
fi
if [[ "$CODESIGN_IDENTITY" != "Developer ID Application:"* ]]; then
  echo "The signing identity must be a Developer ID Application certificate." >&2
  exit 1
fi
if ! security find-identity -v -p codesigning | grep -Fq "\"$CODESIGN_IDENTITY\""; then
  echo "The requested signing identity is not available in the keychain: $CODESIGN_IDENTITY" >&2
  exit 1
fi

if ! xcrun notarytool history --keychain-profile "$NOTARY_PROFILE" >/dev/null; then
  echo "A valid notarytool keychain profile is required: $NOTARY_PROFILE" >&2
  echo "Create it with: xcrun notarytool store-credentials \"$NOTARY_PROFILE\" --apple-id \"YOUR_APPLE_ID\" --team-id \"YOUR_TEAM_ID\"" >&2
  exit 1
fi

export DJI_GYRO_FIX_ARCH="$TARGET_ARCH"
export DJI_GYRO_FIX_CODESIGN_IDENTITY="$CODESIGN_IDENTITY"
export PYINSTALLER_CONFIG_DIR

"$PYTHON_BIN" -m PyInstaller \
  --noconfirm \
  --clean \
  --distpath "$DIST_DIR" \
  --workpath "$BUILD_DIR" \
  "$PROJECT_ROOT/packaging/macos/DJI_Gyro_Fix.spec"

codesign --verify --deep --strict --verbose=2 "$APP_PATH"
SIGNATURE_DETAILS="$(codesign -dv --verbose=4 "$APP_PATH" 2>&1)"
if ! grep -Fq "Authority=Developer ID Application:" <<<"$SIGNATURE_DETAILS"; then
  echo "The app bundle is not signed with Developer ID Application." >&2
  exit 1
fi
if ! grep -Eq 'flags=.*runtime' <<<"$SIGNATURE_DETAILS"; then
  echo "The app bundle is not signed with Hardened Runtime enabled." >&2
  exit 1
fi
if ! grep -Fq "Timestamp=" <<<"$SIGNATURE_DETAILS"; then
  echo "The app bundle signature does not contain a secure timestamp." >&2
  exit 1
fi

mkdir -p "$RELEASE_DIR"
rm -f "$ARCHIVE_PATH" "$RELEASE_DIR/SHA256SUMS.txt"
ditto -c -k --sequesterRsrc --keepParent "$APP_PATH" "$ARCHIVE_PATH"
xcrun notarytool submit "$ARCHIVE_PATH" \
  --keychain-profile "$NOTARY_PROFILE" \
  --wait
xcrun stapler staple "$APP_PATH"
xcrun stapler validate "$APP_PATH"
codesign --verify --deep --strict --verbose=2 "$APP_PATH"
spctl --assess --type execute --verbose=4 "$APP_PATH"

# Recreate the upload archive so the distributed app includes the stapled ticket.
rm -f "$ARCHIVE_PATH"
ditto -c -k --sequesterRsrc --keepParent "$APP_PATH" "$ARCHIVE_PATH"

(
  cd "$RELEASE_DIR"
  shasum -a 256 "$(basename "$ARCHIVE_PATH")" > SHA256SUMS.txt
)

echo "Built app: $APP_PATH"
echo "Release archive: $ARCHIVE_PATH"
echo "Checksum: $RELEASE_DIR/SHA256SUMS.txt"
