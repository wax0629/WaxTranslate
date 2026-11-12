#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
work="$(mktemp -d)"
profile="WaxTranslate.Test.Hover.$(uuidgen)"
cleanup() {
  defaults delete "$profile" >/dev/null 2>&1 || true
  rm -rf "$work"
}
trap cleanup EXIT

bundle="$work/waxtranlate.app"
mkdir -p "$bundle/Contents/MacOS" "$bundle/Contents/Resources"
cp Info.plist "$bundle/Contents/"
cp Assets/Lexicon/reading-terms.json "$bundle/Contents/Resources/"
swiftc -parse-as-library -D WAX_HOVER_CHECKS -target "$(uname -m)-apple-macosx15.2" \
  Sources/waxtranlate/*.swift Tests/Performance/HoverFeedback.swift -o "$bundle/Contents/MacOS/waxtranlate"
python3 scripts/sign-local.py "$bundle" "$HOME/Applications/waxtranlate.app"

images="${1:-$work/images}"
mkdir -p "$images"
open -n -g -W --stderr "$work/check.log" --env "WAX_HOVER_IMAGES=$(cd "$images" && pwd)" "$bundle" \
  --args --test-profile "$profile" --test-hover --test-hover-checks
cat "$work/check.log"
grep -Fq "Passed: pending, same-window result" "$work/check.log"
