#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
out="$(mktemp -d)"
trap 'rm -rf "$out"' EXIT
swiftc -O -parse-as-library -target "$(uname -m)-apple-macosx15.2" \
  Sources/waxtranlate/{Reader,SentenceContext,ContextBoundary,LookupTranslation,LookupTrace,Preferences,Terminology}.swift \
  Tests/Performance/TranslationProbe.swift -o "$out/translation-probe"
"$out/translation-probe" "$@"
