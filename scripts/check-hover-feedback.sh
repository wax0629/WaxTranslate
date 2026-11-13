#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

if [[ "${1:-}" != --desktop ]]; then
  compile() {
    local source="$1" output="$2"
    shift 2
    swiftc -O -whole-module-optimization -parse-as-library -D WAX_APP_TESTS "$@" -target "$(uname -m)-apple-macosx15.2" \
      "$source"/Sources/waxtranlate/*.swift Tests/Performance/OffscreenHover.swift -o "$output"
  }
  if [[ "${1:-}" == --phrase-preview && $# == 3 ]]; then
    baseline="$(git rev-parse --verify "$3^{commit}")"
    mkdir "$work/base"
    git archive "$baseline" Sources Assets/Lexicon | tar -x -C "$work/base"
    compile "$work/base" "$work/before"
    compile . "$work/after" -D WAX_EXPECT_READING_PHRASE
    for version in before after after before before after; do
      echo "version=$version"
      "$work/$version" --phrase-preview "$2/$version"
    done
  elif [[ "${1:-}" == --compare && $# == 2 ]]; then
    baseline="$(git rev-parse --verify "$2^{commit}")"
    mkdir "$work/base"
    git archive "$baseline" Sources | tar -x -C "$work/base"
    compile "$work/base" "$work/baseline" -D WAX_HOVER_BASELINE
    compile . "$work/current"
    for version in baseline current current baseline baseline current; do
      echo "version=$version"
      "$work/$version"
    done
  elif [[ $# == 0 ]]; then
    compile . "$work/current"
    "$work/current"
  else
    echo "Usage: $0 [--compare <previous-commit> | --phrase-preview <directory> <pre-phrase-commit> | --desktop [image-directory]]" >&2
    exit 2
  fi
  exit
fi
shift
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
