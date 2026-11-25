#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
executable="${1:?Supply the compiled executable}"
bundle="${2:?Supply a new app bundle path}"
mkdir -p "$bundle/Contents/MacOS" "$bundle/Contents/Resources"
install -m 755 "$executable" "$bundle/Contents/MacOS/waxtranlate"
cp Info.plist "$bundle/Contents/Info.plist"
cp Assets/Editorial/{river.jpg,glance.png} Assets/Lexicon/reading-terms.json "$bundle/Contents/Resources/"
./scripts/build-icon.sh Assets/Brand/wax-icon.png "$bundle/Contents/Resources/AppIcon.icns"
