// swift-tools-version: 5.10
import PackageDescription

let package = Package(
    name: "waxtranlate",
    platforms: [.macOS("15.2")],
    targets: [
        .executableTarget(name: "waxtranlate")
    ]
)
