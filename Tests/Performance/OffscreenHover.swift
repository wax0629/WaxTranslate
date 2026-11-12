import SwiftUI
import Translation

// Exercises the production OCR, card and translation against known pixels.
// Windows stay unordered, no keyboard monitors are installed, and no display is captured.
@main struct OffscreenHover {
    private static let screen = CGRect(x: 0, y: 0, width: 1400, height: 400)
    private static let scale: CGFloat = 2

    struct Sample {
        let image: CGImage
        let text: String
        let origin: CGPoint
        let font = NSFont.systemFont(ofSize: 24)

        init(_ text: String) {
            self.text = text
            origin = CGPoint(x: 450, y: 180)
            let canvas = CGContext(data: nil, width: Int(screen.width * scale), height: Int(screen.height * scale),
                                   bitsPerComponent: 8, bytesPerRow: 0, space: CGColorSpaceCreateDeviceRGB(),
                                   bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
            canvas.scaleBy(x: scale, y: scale)
            canvas.setFillColor(CGColor(gray: 1, alpha: 1))
            canvas.fill(screen)
            NSGraphicsContext.saveGraphicsState()
            NSGraphicsContext.current = NSGraphicsContext(cgContext: canvas, flipped: false)
            (text as NSString).draw(at: origin, withAttributes: [.font: font, .foregroundColor: NSColor.black])
            NSGraphicsContext.restoreGraphicsState()
            image = canvas.makeImage()!
        }

        func point(_ word: String) -> CGPoint {
            let range = (text as NSString).range(of: word, options: .backwards)
            precondition(range.location != NSNotFound)
            let preceding = (text as NSString).substring(to: range.location) as NSString
            let x = preceding.size(withAttributes: [.font: font]).width + (word as NSString).size(withAttributes: [.font: font]).width / 2
            return CGPoint(x: origin.x + x, y: origin.y + font.ascender * 0.55)
        }

        func crop(_ area: CGRect) -> CGImage {
            let topLeft = Reader.sourceRect(area, on: screen).applying(CGAffineTransform(scaleX: scale, y: scale))
            return image.cropping(to: topLeft.integral)!
        }
    }

    @MainActor static func main() async {
        do { try await run() }
        catch {
            FileHandle.standardError.write(Data("Offscreen lookup failed: \(error)\n".utf8))
            exit(1)
        }
    }

    @MainActor private static func run() async throws {
        NSApplication.shared.setActivationPolicy(.prohibited)
        let suite = "WaxTranslate.Test.OffscreenHover." + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let notebook = Notebook(defaults: defaults), preferences = Preferences(defaults: defaults)
        let window = NSPanel(contentRect: .zero, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        let canTranslate: Bool
        if #available(macOS 26.4, *) {
            canTranslate = await LanguageAvailability().status(from: Locale.Language(identifier: "en"), to: Locale.Language(identifier: "zh-Hans")) == .installed
        } else { canTranslate = false }
        TranslationWarmup.start()
        await Reader.warmUp(language: nil)
        let infection = Sample("These results do not rule out infection.")
        let river = Sample("They sat on the river bank and watched the water.")
        let loan = Sample("The bank approved the loan.")
        var cases: [(String, Sample, String, String, String, LookupResult.Origin)] = [
            ("first", infection, "out", "rule out", "排除", .sentence),
            ("neighbor", infection, "results", "results", "结果", .sentence),
            ("changed", river, "bank", "bank", "岸", .sentence),
            ("other-sense", loan, "bank", "bank", "银行", .sentence),
            ("repeat", loan, "bank", "bank", "银行", .sentence)
        ]
        #if !WAX_HOVER_BASELINE
        cases.append(("shift-key", Sample("Hold down Shift to select text."), "Shift", "Shift", "换挡键", .term))
        cases.append(("work-shift", Sample("Her shift starts at noon."), "shift", "shift", "班", .sentence))
        let cache = Reader.HoverCache()
        #endif
        for (name, sample, token, word, meaning, origin) in cases {
            window.contentView = nil
            let point = sample.point(token)
            let trace = LookupTrace(), began = LookupTrace.now
            let passage: Passage
            #if WAX_HOVER_BASELINE
            let bounds = Reader.hoverRect(at: point, on: screen)
            let target = CGPoint(x: (point.x - bounds.minX) / bounds.width, y: (point.y - bounds.minY) / bounds.height)
            let input = sample.crop(bounds)
            passage = try await Task.detached(priority: .userInitiated) {
                try Reader.recognize(image: input, target: target, isCrop: true)
            }.value
            #else
            passage = try await cache.passage(at: point, on: screen, displayID: 1, language: nil, trace: trace,
                                              image: sample.crop)
            #endif
            guard passage.text == word, passage.context == sample.text,
                  passage.anchor == (sample.text as NSString).range(of: token, options: .backwards), passage.hasCompleteContext else {
                throw failure("Wrong occurrence or context for \(name): \(passage)")
            }
            let term = LookupPolicy(passage).term
            guard origin == .term ? term?.meaning.contains(meaning) == true : term == nil else {
                throw failure("Wrong terminology decision for \(name)")
            }
            let cacheKey = passage.using(language: "en")
            let card = ResultCard(passage: passage, notebook: notebook, preferences: preferences, trace: trace, close: {},
                                  speak: { _, _ in }, focusForDownload: {})
            let host = NSHostingView(rootView: card)
            window.contentView = host
            window.setContentSize(host.fittingSize)
            host.layoutSubtreeIfNeeded()
            let wordTime = (LookupTrace.now - began) * 1000
            var meaningTime = "skipped"
            if canTranslate {
                let deadline = LookupTrace.now + 12
                while LookupCache.shared.result(for: cacheKey) == nil && LookupTrace.now < deadline {
                    try await Task.sleep(nanoseconds: 5_000_000)
                }
                guard let result = LookupCache.shared.result(for: cacheKey), result.origin == origin,
                      result.meaning.contains(meaning), let sentence = result.sentenceTranslation, !sentence.isEmpty,
                      origin == .term || sentence.contains(meaning) else {
                    throw failure("Missing expected contextual translation for \(name)")
                }
                meaningTime = String(format: "%.1f", (LookupTrace.now - began) * 1000)
            }
            guard !window.isVisible else { throw failure("The test panel was ordered on screen") }
            print("sample=\(name) word_ms=\(String(format: "%.1f", wordTime)) meaning_ms=\(meaningTime)")
        }
        window.contentView = nil
        #if !WAX_HOVER_BASELINE
        try await checkChangedPixelsAndCancellation()
        #endif
        if !canTranslate { print("Skipped live contextual meanings: requires macOS 26.4+ and installed EN/ZH models.") }
        print("Passed: \(cases.count) accurate offscreen lookups, including the same word in different contexts.")
    }

    #if !WAX_HOVER_BASELINE
    private static func checkChangedPixelsAndCancellation() async throws {
        let cache = Reader.HoverCache()
        let first = Sample("The bank closed today."), second = Sample("The bark changed color.")
        let point = first.point("bank")
        func read(_ sample: Sample) async throws -> Passage {
            try await cache.passage(at: point, on: screen, displayID: 1, language: nil, trace: LookupTrace(),
                                    image: sample.crop)
        }
        let before = try await read(first), after = try await read(second)
        guard before.text == "bank", after.text == "bark", after.context == second.text else {
            throw failure("New pixels at the same coordinates returned a stale word")
        }
        do {
            _ = try await read(Sample(""))
            throw failure("A blank page returned the preceding word")
        } catch ReaderError.noText {}
        let (started, ready) = AsyncStream<Void>.makeStream()
        let cancelled = Task {
            try await cache.passage(at: point, on: screen, displayID: 1, language: nil, trace: LookupTrace()) { area in
                ready.yield(())
                try await Task.sleep(nanoseconds: 5_000_000_000)
                return second.crop(area)
            }
        }
        for await _ in started { break }
        ready.finish()
        cancelled.cancel()
        do {
            _ = try await cancelled.value
            throw failure("Cancelled lookup produced a word")
        } catch is CancellationError {}
        let recovered = try await read(first)
        guard recovered.text == "bank" else { throw failure("The next lookup failed after cancellation") }
        print("Passed: replacement at identical coordinates, blank crop, cancellation and recovery.")
    }
    #endif

    private static func failure(_ reason: String) -> NSError {
        NSError(domain: "OffscreenHover", code: 1, userInfo: [NSLocalizedDescriptionKey: reason])
    }
}
