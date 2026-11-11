#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
out="$(mktemp -d)"
trap 'rm -rf "$out"' EXIT
swiftc -parse-as-library -target "$(uname -m)-apple-macosx15.2" \
  Sources/waxtranlate/{Reader,SentenceContext,ContextBoundary,CardPresentation,ResultCard,LookupTranslation,ContextWordAlignment,LookupTrace,Notebook,Preferences,References,Reading,DeskTheme,Terminology,Panels}.swift \
  Tests/waxtranlateTests/TrialPreview.swift -o "$out/preview"
"$out/preview" "${1:-docs/verification/public-trial-fixes}"
