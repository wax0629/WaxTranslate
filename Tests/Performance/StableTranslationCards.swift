import SwiftUI
import Translation

extension StableTranslation {
    // Controlled pixels enter production HoverCache, accurate Vision and ResultCard.
    // The panel stays unordered; no screen capture, input monitoring or user defaults.
    struct Canvas {
        static let screen = CGRect(x: 0, y: 0, width: 1400, height: 700)
        let image: CGImage
        let point: CGPoint
        init(_ sample: Sample) {
            let font = NSFont.systemFont(ofSize: 22)
            let storage = NSTextStorage(string: sample.text, attributes: [.font: font, .foregroundColor: NSColor.black])
            let layout = NSLayoutManager(), container = NSTextContainer(size: CGSize(width: 760, height: 400))
            container.lineFragmentPadding = 0
            storage.addLayoutManager(layout); layout.addTextContainer(container)
            layout.ensureLayout(for: container)
            let selected = (sample.text as NSString).range(of: sample.word, options: .backwards)
            let glyphs = layout.glyphRange(forCharacterRange: selected, actualCharacterRange: nil)
            let hit = layout.boundingRect(forGlyphRange: glyphs, in: container)
            let origin = CGPoint(x: 300, y: 260)
            point = CGPoint(x: origin.x + hit.midX, y: Self.screen.height - origin.y - hit.midY)
            let context = CGContext(data: nil, width: 2800, height: 1400, bitsPerComponent: 8, bytesPerRow: 0,
                                    space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
            context.scaleBy(x: 2, y: 2)
            context.setFillColor(CGColor(gray: 1, alpha: 1)); context.fill(Self.screen)
            context.translateBy(x: 0, y: Self.screen.height); context.scaleBy(x: 1, y: -1)
            NSGraphicsContext.saveGraphicsState()
            NSGraphicsContext.current = NSGraphicsContext(cgContext: context, flipped: true)
            layout.drawGlyphs(forGlyphRange: NSRange(location: 0, length: layout.numberOfGlyphs), at: origin)
            NSGraphicsContext.restoreGraphicsState()
            image = context.makeImage()!
        }
        func crop(_ area: CGRect) -> CGImage {
            image.cropping(to: Reader.sourceRect(area, on: Self.screen).applying(CGAffineTransform(scaleX: 2, y: 2)).integral)!
        }
    }

    struct CardReport: Encodable {
        let id: String
        let iteration: Int
        let milliseconds: Double
        let wordMs: Double
        let firstReferenceMs: Double?
        let meaning, origin, sentence, source, word: String
        let quality, cacheHit: Bool
        let selectionCorrect: Bool
        let events: [LookupTrace.Event]
    }

    @MainActor static func cards(_ samples: [Sample]) async throws {
        NSApplication.shared.setActivationPolicy(.prohibited)
        let suite = "WaxTranslate.Test.Stable." + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let notebook = Notebook(defaults: defaults), preferences = Preferences(defaults: defaults)
        let window = NSPanel(contentRect: .zero, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        defer { window.contentView = nil; window.close() }
        let cache = Reader.HoverCache()
        if ProcessInfo.processInfo.environment["WAX_BENCH_COLD"] != "1" {
            TranslationWarmup.start()
            await Reader.warmUp(language: nil)
        }
        for iteration in 1...(Int(ProcessInfo.processInfo.environment["WAX_BENCH_REPEATS"] ?? "1") ?? 1) {
            for sample in samples {
                window.contentView = nil
                let canvas = Canvas(sample)
                if let directory = ProcessInfo.processInfo.environment["WAX_BENCH_IMAGES"], iteration == 1 {
                    try FileManager.default.createDirectory(atPath: directory, withIntermediateDirectories: true)
                    let bitmap = NSBitmapImageRep(cgImage: canvas.image)
                    try bitmap.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: directory).appendingPathComponent(sample.id + "-source.png"))
                    FileHandle.standardError.write(Data("\(sample.id) pointer=\(canvas.point)\n".utf8))
                }
                let trace = LookupTrace(capture: true), began = LookupTrace.now
                var passage = try await cache.passage(at: canvas.point, on: Canvas.screen, displayID: 1, language: nil, trace: trace, image: canvas.crop)
                if let phrase = sample.phrase {
                    let range = (passage.context as NSString).range(of: phrase)
                    guard let selected = passage.selecting(range, anchor: passage.anchor) else { throw CocoaError(.fileReadCorruptFile) }
                    passage = selected
                }
                let cacheKey = passage.using(language: passage.sourceLanguage)
                let cacheHit = LookupCache.shared.result(for: cacheKey) != nil
                let host = NSHostingView(rootView: ResultCard(passage: passage, notebook: notebook, preferences: preferences, trace: trace,
                                                             close: {}, speak: { _, _ in }, focusForDownload: {}).environment(\.colorScheme, .light))
                window.contentView = host
                window.setContentSize(host.fittingSize); host.layoutSubtreeIfNeeded()
                let wordMs = (LookupTrace.now - began) * 1000
                if iteration == 1 { try snapshot(host, window: window, name: sample.id + "-pending") }
                var firstCaptured = false
                while LookupCache.shared.result(for: cacheKey) == nil && LookupTrace.now - began < 15 {
                    if !firstCaptured, trace.snapshot.contains(where: { $0.stage == "lookup.first_reference" }) {
                        if iteration == 1 { try snapshot(host, window: window, name: sample.id + "-first") }
                        firstCaptured = true
                    }
                    if trace.snapshot.contains(where: { $0.stage == "lookup.complete" }) { break }
                    try await Task.sleep(for: .milliseconds(2))
                }
                host.layoutSubtreeIfNeeded()
                let elapsed = (LookupTrace.now - began) * 1000
                let result = LookupCache.shared.result(for: cacheKey)
                if iteration == 1 { try snapshot(host, window: window, name: sample.id + "-final") }
                guard !window.isVisible else { throw CocoaError(.executableNotLoadable) }
                let events = trace.snapshot
                let expected = try sample.passage()
                let selectionCorrect = passage.text == expected.text && passage.context == expected.context && passage.selection == expected.selection && passage.hasCompleteContext
                let report = CardReport(id: sample.id, iteration: iteration, milliseconds: elapsed, wordMs: wordMs,
                                        firstReferenceMs: events.first(where: { $0.stage == "lookup.first_reference" })?.elapsedMs,
                                        meaning: result?.meaning ?? "", origin: result.map { String(describing: $0.origin) } ?? "unresolved",
                                        sentence: result?.sentenceTranslation ?? "", source: passage.context, word: passage.text,
                                        quality: selectionCorrect && (result.map { value in sample.expected.contains(where: value.meaning.contains) } ?? false),
                                        cacheHit: cacheHit, selectionCorrect: selectionCorrect, events: events)
                let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys]
                print(String(decoding: try encoder.encode(report), as: UTF8.self)); fflush(stdout)
            }
        }
    }

    @MainActor static func snapshot(_ host: NSView, window: NSWindow, name: String) throws {
        guard let directory = ProcessInfo.processInfo.environment["WAX_BENCH_IMAGES"] else { return }
        let output = URL(fileURLWithPath: directory)
        try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
        window.setContentSize(host.fittingSize); host.layoutSubtreeIfNeeded()
        guard let bitmap = host.bitmapImageRepForCachingDisplay(in: host.bounds) else { throw CocoaError(.fileWriteUnknown) }
        host.cacheDisplay(in: host.bounds, to: bitmap)
        guard let png = bitmap.representation(using: .png, properties: [:]) else { throw CocoaError(.fileWriteUnknown) }
        try png.write(to: output.appendingPathComponent(name + ".png"))
    }
}
