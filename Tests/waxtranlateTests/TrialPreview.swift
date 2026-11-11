import AppKit
import SwiftUI
import Translation

// Evidence captures use real native views and the installed Apple service in
// an isolated preferences domain. Nothing is installed or sent to the desktop.
@main @MainActor struct TrialPreview {
    static func main() async throws {
        NSApplication.shared.setActivationPolicy(.prohibited)
        NSApplication.shared.appearance = NSAppearance(named: .aqua)
        guard #available(macOS 26.4, *),
              await LanguageAvailability().status(from: Locale.Language(identifier: "en"), to: Locale.Language(identifier: "zh-Hans")) == .installed else {
            print("Skipped preview: requires installed Apple EN/ZH and macOS 26.4+.")
            exit(77)
        }
        let output = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
        try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
        let suite = "WaxTranslate.Test.trial-preview." + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let book = Notebook(defaults: defaults)
        let preferences = Preferences(defaults: defaults)
        let session = TranslationSession(installedSource: Locale.Language(identifier: "en"), target: Locale.Language(identifier: "zh-Hans"))
        let text = "After a very long walk through the quiet village and past the old houses where people were preparing for the evening, they sat on the river bank and watched the water flow slowly toward the distant mountains."
        let passage = Passage(text: "bank", context: text, language: "en")
        let bankResult = try await LookupTranslation.translate(passage, session: session, dictionary: [])
        guard bankResult.origin == .sentence, bankResult.meaning.contains("岸"), bankResult.wordReference == nil,
              bankResult.canSave(for: passage) else { fatalError("Long bank must have a usable river sense") }
        print("Actual long-bank result:", bankResult.origin, bankResult.meaning, "secondary:", bankResult.wordReference ?? "none")
        try capture(output.appendingPathComponent("mac-long-bank.png")) {
            AnyView(ResultCard(passage: passage, notebook: book, preferences: preferences, initialResult: bankResult, close: {}, speak: { _, _ in }, focusForDownload: {}))
        }
        let region = Passage(text: "The sample contains a green triangle.", context: "", language: "en")
        let regionResult = try await LookupTranslation.translate(region, session: session, dictionary: [])
        try capture(output.appendingPathComponent("mac-region.png")) {
            AnyView(ResultCard(passage: region, notebook: book, preferences: preferences, initialResult: regionResult, close: {}, speak: { _, _ in }, focusForDownload: {}))
        }
        // A mounted, confirmed word may record one lookup while rendering;
        // region translation still must not appear as a recent word.
        guard book.totalLookups <= 1, book.entries.isEmpty,
              book.recent.allSatisfy({ $0.word == passage.text }) else { fatalError("Unexpected notebook write while capturing native cards") }
        print("Native evidence captured; lookup count:", book.totalLookups, "saved entries:", book.entries.count)
    }

    private static func capture(_ path: URL, content: () -> AnyView) throws {
        // Preload the actual provider result; no live geometry feedback or
        // second translation is needed to export the settled native view.
        let host = NSHostingView(rootView: content().environment(\.colorScheme, .light))
        let size = host.fittingSize
        guard size.width == 365, size.height > 90, size.height < 650 else { fatalError("Invalid preview layout: \(size)") }
        host.frame = CGRect(origin: .zero, size: size)
        host.layoutSubtreeIfNeeded()
        guard let bitmap = host.bitmapImageRepForCachingDisplay(in: host.bounds) else { throw CocoaError(.fileWriteUnknown) }
        host.cacheDisplay(in: host.bounds, to: bitmap)
        guard let png = bitmap.representation(using: .png, properties: [:]) else { throw CocoaError(.fileWriteUnknown) }
        try png.write(to: path)
    }
}
