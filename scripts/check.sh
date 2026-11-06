#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
out="$(mktemp -d)"
trap 'rm -rf "$out"' EXIT
swiftc -parse-as-library -target "$(uname -m)-apple-macosx15.2" \
  Sources/waxtranlate/{Reader,SentenceContext,LookupTranslation,Notebook}.swift Tests/waxtranlateTests/ReaderTests.swift \
  -o "$out/check"
"$out/check"
