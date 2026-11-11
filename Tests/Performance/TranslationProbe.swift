import Foundation
import Translation

@main struct TranslationProbe {
    static func main() async throws {
        guard #available(macOS 26.4, *) else { print("Skipped: requires macOS 26.4+."); return }
        let source = Locale.Language(identifier: "en"), target = Locale.Language(identifier: "zh-Hans")
        guard await LanguageAvailability().status(from: source, to: target) == .installed else {
            print("Skipped: EN/ZH languages are not installed."); return
        }
        let shared = CommandLine.arguments.contains("--reuse-session") ? TranslationSession(installedSource: source, target: target) : nil
        let longContext = CommandLine.arguments.contains("--long-context")
        for index in 1...3 {
            let session = shared ?? TranslationSession(installedSource: source, target: target)
            let trace = LookupTrace(enabled: true), began = LookupTrace.now
            try await session.prepareTranslation()
            trace.record("translation.prepare", since: began)
            let passage = longContext
                ? Passage(text: "bank", context: "After a very long walk through the quiet village and past the old houses where people were preparing for the evening, they sat on the river bank and watched the water flow slowly toward the distant mountains.", language: "en")
                : Passage(text: "INTEGER", context: "The INTEGER value must be positive.", language: "en")
            let result = try await LookupTranslation.translate(passage, session: session, dictionary: [], trace: trace)
            trace.record("lookup.complete", since: began)
            print("Query", index, result.meaning, result.sentenceTranslation ?? "")
        }
    }
}
