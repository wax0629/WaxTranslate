#!/bin/bash
set -euo pipefail
source_png="${1:?Specify the square source PNG}"
output_icns="${2:?Specify the destination .icns file}"
icon_stage="$(mktemp -d)"
trap 'rm -rf "$icon_stage"' EXIT
iconset="$icon_stage/AppIcon.iconset"
mkdir "$iconset"

for size in 16 32 128 256 512; do
  /usr/bin/sips -Z "$size" "$source_png" --out "$iconset/icon_${size}x${size}.png" >/dev/null
  /usr/bin/sips -Z "$((2 * size))" "$source_png" --out "$iconset/icon_${size}x${size}@2x.png" >/dev/null
done
/usr/bin/iconutil -c icns "$iconset" -o "$output_icns"
