#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
out="$(mktemp -d)"
trap 'rm -rf "$out"' EXIT
swiftc -parse-as-library -D WAX_APP_TESTS -target "$(uname -m)-apple-macosx15.2" \
  Sources/waxtranlate/*.swift Tests/waxtranlateTests/{AppPermissions,ReferenceTests}.swift -o "$out/check"
"$out/check"
