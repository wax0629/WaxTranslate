#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
out="$(mktemp -d)"
trap 'rm -rf "$out"' EXIT
swiftc -parse-as-library -D LONG_CONTEXT_STANDALONE -target "$(uname -m)-apple-macosx15.2" \
  Sources/waxtranlate/{Reader,SentenceContext,ContextBoundary,CardPresentation,LookupTranslation,ContextWordAlignment,LookupTrace,Notebook,Preferences,References,Reading,DeskTheme,Terminology}.swift \
  Tests/waxtranlateTests/LongContextTests.swift -o "$out/check"
"$out/check"
