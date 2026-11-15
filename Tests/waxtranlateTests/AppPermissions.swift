import AppKit
import SwiftUI
import Translation

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
        try await automaticCancellation(defaults: defaults)
    }

    private static func automaticCancellation(defaults: UserDefaults) async throws {
        guard #available(macOS 26.0, *), await LanguageAvailability().status(from: Locale.Language(identifier: "en"),
                                                                           to: Locale.Language(identifier: "zh-Hans")) == .installed else {
            print("Skipped: native worker cancellation requires an installed EN/ZH model.")
            return
        }
        let source = "Before the afternoon visitors arrived, she deposited her paycheck at the bank."
        let cancelled = Passage(text: "bank", context: source, language: "en")
        let worker = AutomaticLookup.start(cancelled, trace: LookupTrace())!
        worker.cancel()
        do { _ = try await worker.task.value; fatalError("Cancelled worker returned a publishable result") }
        catch { guard worker.task.isCancelled else { throw error } }
        guard LookupCache.shared.result(for: cancelled) == nil else { fatalError("Worker wrote the UI cache") }
        let book = Notebook(defaults: defaults), preferences = Preferences(defaults: defaults)
        let panel = NSPanel(contentRect: .zero, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        defer { panel.contentView = nil; panel.close() }
        let trace = LookupTrace(capture: true)
        panel.contentView = NSHostingView(rootView: ResultCard(passage: cancelled, notebook: book, preferences: preferences, trace: trace,
                                                              close: {}, speak: { _, _ in }, focusForDownload: {}))
        panel.contentView?.layoutSubtreeIfNeeded()
        await Task.yield()
        panel.contentView = nil
        let replacement = Passage(text: "bank", context: "Before the afternoon visitors arrived, they rested on the river bank.", language: "en")
        panel.contentView = NSHostingView(rootView: ResultCard(passage: replacement, notebook: book, preferences: preferences,
                                                              close: {}, speak: { _, _ in }, focusForDownload: {}))
        let deadline = LookupTrace.now + 15
        while LookupCache.shared.result(for: replacement) == nil && LookupTrace.now < deadline { try await Task.sleep(for: .milliseconds(10)) }
        guard let result = LookupCache.shared.result(for: replacement), result.origin == .sentence, result.meaning.contains("岸"),
              LookupCache.shared.result(for: cancelled) == nil,
              !trace.snapshot.contains(where: { $0.stage == "lookup.complete" }),
              book.recent.count == 1, book.recent.first?.meaning.contains("岸") == true,
              !panel.isVisible else { fatalError("Replacing a card published a cancelled/stale result or opened a window") }
        print("Passed: detached native worker cancellation, replaced card cannot publish/cache/save, replacement keeps its own river sense (offscreen).")
    }
}
