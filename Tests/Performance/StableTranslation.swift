import Foundation
import Translation
import ScreenCaptureKit

@main struct StableTranslation {
    struct Sample: Decodable {
        let id, text, word: String
        let phrase: String?
        let expected: [String]
        func passage() throws -> Passage {
            let hit = (text as NSString).range(of: word, options: .backwards)
            let passage = try SentenceContext.passage(in: text, selection: hit, language: "en")
            guard let phrase else { return passage }
            let range = (passage.context as NSString).range(of: phrase)
            return Passage(text: phrase, context: passage.context, selection: range, anchor: passage.anchor, language: "en")
        }
    }
    struct Report: Encodable {
        let id: String
        let iteration: Int
        let milliseconds: Double
        let meaning, origin, sentence: String
        let quality: Bool?
        let dictionary: [String]
        let events: [LookupTrace.Event]
    }
    @MainActor static func main() async throws {
        guard #available(macOS 26.4, *) else { throw CocoaError(.featureUnsupported) }
        if ProcessInfo.processInfo.environment["WAX_BENCH_MODE"] == "capture" {
            try await captureTiming()
            return
        }
        // A reusable baseline must carry its own lexicon after the temporary
        // archived source is removed. Fail instead of timing a degraded build.
        guard Bundle.main.url(forResource: "reading-terms", withExtension: "json") != nil else { throw CocoaError(.fileReadNoSuchFile) }
        let samples = try JSONDecoder().decode([Sample].self, from: Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1])))
        let source = Locale.Language(identifier: "en"), target = Locale.Language(identifier: "zh-Hans")
        guard await LanguageAvailability().status(from: source, to: target) == .installed else { throw CocoaError(.featureUnsupported) }
        let session = TranslationSession(installedSource: source, target: target)
        if ProcessInfo.processInfo.environment["WAX_BENCH_MODE"] == "cards" {
            try await cards(samples)
            return
        }
        for iteration in 1...(Int(ProcessInfo.processInfo.environment["WAX_BENCH_REPEATS"] ?? "1") ?? 1) {
            for sample in samples {
                let trace = LookupTrace(capture: true), began = LookupTrace.now
                let passage = try sample.passage()
                trace.record("lookup.selection", since: began)
                let dictionary = Task.detached { () -> [String] in
                    let start = LookupTrace.now
                    let references = await CompactGloss.references(for: passage)
                    trace.record("lookup.dictionary", since: start)
                    return references
                }
                let prepare = LookupTrace.now
                try await session.prepareTranslation()
                trace.record("translation.prepare", since: prepare)
                let result = try await LookupTranslation.translate(passage, session: session, dictionary: await dictionary.value, trace: trace)
                let milliseconds = (LookupTrace.now - began) * 1000
                let report = Report(id: sample.id, iteration: iteration, milliseconds: milliseconds,
                                    meaning: result.meaning, origin: String(describing: result.origin), sentence: result.sentenceTranslation ?? "",
                                    quality: sample.expected.isEmpty ? nil : result.isUsable && sample.expected.contains(where: result.meaning.contains),
                                    dictionary: await dictionary.value, events: trace.snapshot)
                let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys]
                print(String(decoding: try encoder.encode(report), as: UTF8.self))
                fflush(stdout)
            }
        }
    }

    // Measure the real screen-acquisition component without opening windows or
    // saving user pixels. Run only from a locally signed bundle already granted
    // screen access; this probe never requests or changes permissions.
    @MainActor private static func captureTiming() async throws {
        NSApplication.shared.setActivationPolicy(.prohibited)
        guard CGPreflightScreenCaptureAccess(), let screen = NSScreen.main,
              let display = Reader.Display(at: CGPoint(x: screen.frame.midX, y: screen.frame.midY)) else { throw ReaderError.permission }
        for iteration in 1...5 {
            let trace = LookupTrace(capture: true), began = LookupTrace.now
            let available = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
            trace.record("capture.enumerate", since: began)
            guard let source = available.displays.first(where: { $0.displayID == display.id }) else { throw ReaderError.noScreen }
            let filter = SCContentFilter(display: source, excludingApplications: available.applications, exceptingWindows: [])
            let point = CGPoint(x: display.frame.midX, y: display.frame.midY)
            let capture = LookupTrace.now
            #if WAX_BENCH_BASELINE
            _ = try await SCScreenshotManager.captureImage(contentFilter: filter, configuration: Reader.screenshotConfiguration(bounds: Reader.hoverRect(at: point, on: display.frame), screen: display.frame, scale: display.scale))
            #else
            _ = try await Reader.screenshot(filter: filter, bounds: Reader.hoverRect(at: point, on: display.frame), screen: display.frame, scale: display.scale)
            #endif
            trace.record("capture.image", since: capture)
            let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys]
            print(String(decoding: try encoder.encode(["iteration": Double(iteration), "milliseconds": (LookupTrace.now - began) * 1000]), as: UTF8.self))
            print(String(decoding: try encoder.encode(trace.snapshot), as: UTF8.self)); fflush(stdout)
        }
    }
}
