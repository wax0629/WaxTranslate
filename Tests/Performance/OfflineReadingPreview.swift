import SwiftUI

// Render just the application's native reading view when the test runner has no screen recording permission.
@main @MainActor struct OfflineReadingPreview {
    static func main() async throws {
        let output = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
        _ = NSApplication.shared
        NSApp.appearance = NSAppearance(named: .aqua)
        let suite = "WaxTranslate.Test.preview." + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let document = ReadingDocument()
        let view = ReadingPage(document: document, preferences: Preferences(defaults: defaults), lookup: { _ in }, speak: { _, _ in })
        let window = NSWindow(contentRect: CGRect(x: 0, y: 0, width: 900, height: 500), styleMask: [.borderless], backing: .buffered, defer: false)
        let host = NSHostingView(rootView: view.background(DeskTheme.paper).environment(\.colorScheme, .light))
        window.contentView = host
        func save(_ name: String) throws {
            host.layoutSubtreeIfNeeded()
            guard let bitmap = host.bitmapImageRepForCachingDisplay(in: host.bounds) else { throw CocoaError(.fileWriteUnknown) }
            host.cacheDisplay(in: host.bounds, to: bitmap)
            guard let png = bitmap.representation(using: .png, properties: [:]) else { throw CocoaError(.fileWriteUnknown) }
            try png.write(to: output.appendingPathComponent(name))
        }
        try save("before.png")
        for (source, language, expected, name) in [("Thank you.", "en", "谢", "english.png"), ("谢谢你。", "zh-Hans", "thank", "chinese.png")] {
            guard BundledTranslation(source: language) != nil else { throw CocoaError(.fileNoSuchFile) }
            document.text = source
            document.begin(language: language)
            let deadline = Date().addingTimeInterval(30)
            while document.busy && Date() < deadline { try await Task.sleep(for: .milliseconds(50)) }
            guard document.translation.lowercased().contains(expected) else { throw CocoaError(.fileReadCorruptFile) }
            try await Task.sleep(for: .milliseconds(100))
            try save(name)
        }
    }
}
