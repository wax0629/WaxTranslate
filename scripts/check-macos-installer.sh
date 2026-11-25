#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
dmg="${1:?Supply the built DMG}"
evidence="${2:-}"
tmp="$(mktemp -d)"
volume="$tmp/mount"
mkdir "$volume" "$tmp/Applications"
profile="WaxTranslate.Test.$(uuidgen)"
app_pid=""
cleanup() {
    if [[ -n "$app_pid" ]]; then kill "$app_pid" 2>/dev/null || true; wait "$app_pid" 2>/dev/null || true; fi
    /usr/bin/defaults delete "$profile" 2>/dev/null || true
    if mount | grep -Fq " on $volume "; then hdiutil detach "$volume" >/dev/null; fi
    rm -rf "$tmp"
}
trap cleanup EXIT
hdiutil attach -readonly -nobrowse -mountpoint "$volume" "$dmg" >/dev/null
app="$tmp/Applications/waxtranlate.app"
ditto "$volume/waxtranlate.app" "$app"
hdiutil detach "$volume" >/dev/null
codesign --verify --deep --strict "$app"
exe="$app/Contents/MacOS/waxtranlate"
lib="$app/Contents/Frameworks/libWaxTranslation.dylib"
for binary in "$exe" "$lib"; do
    lipo "$binary" -verify_arch arm64 x86_64
done
otool -L "$lib"
policy='(version 1)(allow default)(deny network*)'
/usr/bin/sandbox-exec -p "$policy" "$(command -v python3)" macos/check-engine.py "$app"
if [[ "$evidence" == --engine-only ]]; then exit 0; fi
swiftc Tests/Performance/OfflineInstall.swift -o "$tmp/reading-check"
# The unmodified installed executable starts with a new, isolated preferences suite.
# The app and its descendants cannot open a network connection.
PATH=/usr/bin:/bin /usr/bin/sandbox-exec -p "$policy" \
    "$exe" --test-profile "$profile" >"$tmp/app.log" 2>&1 &
app_pid=$!
"$tmp/reading-check" "$app_pid"
if [[ -n "$evidence" ]]; then
    mkdir -p "$evidence"
    preview="$tmp/preview.app/Contents"
    mkdir -p "$preview/MacOS"
    cp "$app/Contents/Info.plist" "$preview/"
    ln -s "$app/Contents/Resources" "$preview/Resources"
    ln -s "$app/Contents/Frameworks" "$preview/Frameworks"
    swiftc -parse-as-library -D WAX_APP_TESTS -target "$(uname -m)-apple-macosx15.2" \
        Sources/waxtranlate/*.swift Tests/Performance/OfflineReadingPreview.swift -o "$preview/MacOS/waxtranlate"
    /usr/bin/sandbox-exec -p "$policy" "$preview/MacOS/waxtranlate" "$evidence"
fi
