import AppKit
import SwiftUI

// Render the actual ResultCard offscreen with fixed, declared data. This is a
// layout fixture, not an OCR/model accuracy test, and sends no desktop input.
@main @MainActor struct CardLayouts {
    static func main() throws {
        let app = NSApplication.shared
        app.setActivationPolicy(.prohibited)
        app.appearance = NSAppearance(named: .aqua)
        let output = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
        try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
        let suite = "WaxTranslate.Test.layouts." + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let book = Notebook(defaults: defaults)
        let preferences = Preferences(defaults: defaults)
        let comment = "Explicit transport views avoid exposing future domain fields by accident."
        let samples: [(String, Passage, LookupResult?)] = [
            ("word", Passage(text: "bank", context: "They sat on the river bank and watched the water.", language: "en"),
             LookupResult(meaning: "岸边", origin: .sentence, sentenceTranslation: "他们坐在河岸边，看着水流。")),
            ("name", Passage(text: "VoiceOver", context: "在macOS辅助功能中启用VoiceOver。", language: "zh-Hans"), nil),
            ("mixed", Passage(text: "Redis", context: "用Docker部署Redis，通过API访问缓存。", language: "zh-Hans"), nil),
            ("unknown", Passage(text: "UnknownSDK", context: "用Docker部署UnknownSDK。", language: "zh-Hans"), nil),
            ("title", Passage(text: "door", context: "Keep this door closed", language: "en", structure: .title),
             LookupResult(meaning: "门", origin: .dictionary)),
            ("whole-title", Passage(text: "Keep this door closed", context: "", language: "en", structure: .title),
             LookupResult(meaning: "请保持这扇门关闭。", origin: .region)),
            ("comment", Passage(text: "avoid", context: comment, language: "en"),
             LookupResult(meaning: "避免", origin: .sentence, sentenceTranslation: "显式传输视图避免意外暴露未来的领域字段。"))
        ]
        var manifest: [[String: Any]] = []
        for (name, passage, fixture) in samples {
            if let fixture { LookupCache.shared.insert(fixture, for: passage) }
            let card = ResultCard(passage: passage, notebook: book, preferences: preferences, close: {}, speak: { _, _ in }, focusForDownload: {})
            let host = NSHostingView(rootView: card)
            let size = host.fittingSize
            host.frame = CGRect(origin: .zero, size: size)
            host.layoutSubtreeIfNeeded()
            guard size.width == 365, size.height > 90, size.height < 650,
                  let bitmap = host.bitmapImageRepForCachingDisplay(in: host.bounds) else {
                throw NSError(domain: "CardLayouts", code: 1, userInfo: [NSLocalizedDescriptionKey: "Invalid card layout: \(name) \(size)"])
            }
            host.cacheDisplay(in: host.bounds, to: bitmap)
            guard let png = bitmap.representation(using: .png, properties: [:]) else { throw CocoaError(.fileWriteUnknown) }
            try png.write(to: output.appendingPathComponent("mac-\(name).png"))
            manifest.append(["case": name, "width": size.width, "height": size.height,
                             "pixels": [bitmap.pixelsWide, bitmap.pixelsHigh],
                             "source": passage.context, "query": passage.text,
                             "kind": "native-view-layout-fixture", "knownMeaningFixture": fixture?.meaning ?? "local terminology or unresolved policy"])
        }
        let data = try JSONSerialization.data(withJSONObject: manifest, options: [.prettyPrinted, .sortedKeys])
        try data.write(to: output.appendingPathComponent("manifest.json"))
        print("Passed: \(samples.count) native card layouts, offscreen; no mouse/keyboard input or user preferences.")
    }
}
