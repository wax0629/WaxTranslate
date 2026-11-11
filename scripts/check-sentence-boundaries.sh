#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
out="$(mktemp -d)"
trap 'rm -rf "$out"' EXIT
flags=(-D BOUNDARY_CURRENT)
if [[ "${WAX_BOUNDARY_BASELINE:-0}" == 1 ]]; then flags+=(-D BOUNDARY_BASELINE); fi
sources=(Sources/waxtranlate/{Reader,SentenceContext,CardPresentation,LookupTranslation,ContextWordAlignment,LookupTrace,Notebook,Preferences,References,Reading,DeskTheme,Terminology,Shortcuts}.swift)
if [[ -f Sources/waxtranlate/ContextBoundary.swift ]]; then sources+=(Sources/waxtranlate/ContextBoundary.swift); fi
swiftc -parse-as-library -target "$(uname -m)-apple-macosx15.2" "${flags[@]}" \
  "${sources[@]}" Tests/waxtranlateTests/SentenceBoundaryTests.swift -o "$out/boundaries"
"$out/boundaries" Tests/Fixtures/sentence-boundaries.json
