#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
source=.
flags=(-D WAX_APP_TESTS)
if [[ $# -gt 0 ]]; then
  baseline="$(git rev-parse --verify "$1^{commit}")"
  source="$work/base"
  mkdir "$source"
  git archive "$baseline" Sources Assets/Lexicon | tar -x -C "$source"
  cp Sources/waxtranlate/LookupTrace.swift "$source/Sources/waxtranlate/LookupTrace.swift"
  flags+=(-D WAX_BENCH_BASELINE)
fi
bundle="${WAX_BENCH_BUNDLE:-$work/StableTranslation.app}"
mkdir -p "$bundle/Contents/MacOS" "$bundle/Contents/Resources"
cp Info.plist "$bundle/Contents/Info.plist"
cp "$source/Assets/Lexicon/reading-terms.json" "$bundle/Contents/Resources/"
cp Tests/Fixtures/stable-translation.json "$bundle/Contents/Resources/"
binary="$bundle/Contents/MacOS/waxtranlate"
swiftc -O -whole-module-optimization -parse-as-library "${flags[@]}" -target "$(uname -m)-apple-macosx15.2" \
  "$source"/Sources/waxtranlate/*.swift \
  Tests/Performance/{StableTranslation,StableTranslationCards}.swift -o "$binary"
if [[ "${WAX_BENCH_COMPILE_ONLY:-0}" == 1 ]]; then exit; fi
"$binary" "${WAX_BENCH_FIXTURES:-Tests/Fixtures/stable-translation.json}"
