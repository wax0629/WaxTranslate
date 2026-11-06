#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
swift build -c release
apps="$HOME/Applications"
mkdir -p "$apps"
stage="$(mktemp -d "$apps/.waxtranlate-install.XXXXXX")"
trap 'rm -rf "$stage"' EXIT
bundle="$stage/waxtranlate.app"
mkdir -p "$bundle/Contents/MacOS"
install -m 755 "$(swift build -c release --show-bin-path)/waxtranlate" "$bundle/Contents/MacOS/waxtranlate"
cp Info.plist "$bundle/Contents/Info.plist"
/usr/bin/python3 scripts/sign-local.py "$bundle" "$apps/waxtranlate.app"

swift - "$bundle" "$apps/waxtranlate.app" "$apps/浮光译.app" <<'SWIFT'
import AppKit

let files = FileManager.default
let id = "local.luma.hovertranslate" // Retain the previous preferences domain and vocabulary.
let paths = CommandLine.arguments.dropFirst().map { URL(fileURLWithPath: $0).standardizedFileURL }
let (staged, destination, previousName) = (paths[0], paths[1], paths[2])
func stop(_ reason: String) -> Never {
    FileHandle.standardError.write(Data((reason + "\n").utf8))
    exit(1)
}
if files.fileExists(atPath: destination.path), Bundle(url: destination)?.bundleIdentifier != id {
    stop("目标位置已有其他应用：" + destination.path)
}
let ours = NSRunningApplication.runningApplications(withBundleIdentifier: id).filter {
    guard let url = $0.bundleURL?.standardizedFileURL else { return false }
    return [destination.path, previousName.path].contains(url.path)
}
for app in ours { _ = app.terminate() }
let deadline = Date().addingTimeInterval(6)
while ours.contains(where: { !$0.isTerminated }), Date() < deadline {
    RunLoop.current.run(until: Date().addingTimeInterval(0.1))
}
if ours.contains(where: { !$0.isTerminated }) { stop("请先退出正在运行的旧版本。") }
if files.fileExists(atPath: destination.path) {
    _ = try files.replaceItemAt(destination, withItemAt: staged, options: .usingNewMetadataOnly)
} else {
    try files.moveItem(at: staged, to: destination)
}
if Bundle(url: previousName)?.bundleIdentifier == id {
    try files.trashItem(at: previousName, resultingItemURL: nil)
}
print(destination.path)
SWIFT
