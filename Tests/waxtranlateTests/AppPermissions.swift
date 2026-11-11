import AppKit
import SwiftUI

// Exercises the app's real permission/error/reset path offscreen. It never
// calls the system permission prompt or installs global keyboard monitors.
@main @MainActor struct AppPermissions {
    static func main() async throws {
        NSApplication.shared.setActivationPolicy(.prohibited)
        let suite = "WaxTranslate.Test.permission." + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        var granted = false
        let app = App(defaults: defaults, captureAccess: { granted })
        guard !app.readyToCapture(), let first = app.testPanel else { fatalError("Missing first permission hint") }
        first.close()
        guard app.testPanel == nil else { fatalError("Close must clear the old hint") }
        guard !app.readyToCapture(), let second = app.testPanel, second !== first else { fatalError("Retry was silent") }
        guard !app.readyToCapture(), let third = app.testPanel, third !== second,
              first.contentView == nil, second.contentView == nil else { fatalError("Overlapping hints") }
        third.close()
        granted = true
        guard app.readyToCapture(), app.testPanel == nil else { fatalError("Permission recovery failed") }
        granted = false
        guard !app.readyToCapture(), app.testPanel != nil else { fatalError("Permission revocation was silent") }
        app.testPanel?.close()
        print("Passed: initial denial, close/retry, replacement, grant and revocation; no system permission changes.")
        try await ReferenceTests.run()
    }
}
