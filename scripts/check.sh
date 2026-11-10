#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
/usr/bin/python3 scripts/sync-reading-terms.py --check
out="$(mktemp -d)"
trap 'rm -rf "$out"' EXIT
swiftc -parse-as-library -target "$(uname -m)-apple-macosx15.2" \
  Sources/waxtranlate/{Reader,SentenceContext,CardPresentation,LookupTranslation,LookupTrace,Notebook,Preferences,References,Reading,DeskTheme,Terminology,Shortcuts}.swift Tests/waxtranlateTests/ReaderTests.swift \
  -o "$out/check"
"$out/check"
