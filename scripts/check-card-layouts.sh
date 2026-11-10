#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
out="$(mktemp -d)"
trap 'rm -rf "$out"' EXIT
swiftc -parse-as-library -target "$(uname -m)-apple-macosx15.2" \
  Sources/waxtranlate/{Reader,SentenceContext,CardPresentation,ResultCard,LookupTranslation,LookupTrace,Notebook,Preferences,References,Reading,DeskTheme,Terminology}.swift \
  Tests/waxtranlateTests/CardLayouts.swift -o "$out/layouts"
"$out/layouts" "${1:-$out/images}"
