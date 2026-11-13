import Foundation
import Translation

// The external corpus and its sentences stay outside the app and repository.
@main struct PhraseCorpus {
    struct Sample: Decodable {
        let id, text, word, phrase: String
    }
    @MainActor static func main() async throws {
        guard CommandLine.arguments.count >= 2 else { throw CocoaError(.fileReadNoSuchFile) }
        let input = try Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))
        let samples = try JSONDecoder().decode([Sample].self, from: input)
        let scored = CommandLine.arguments.contains("--meanings")
        var session: TranslationSession?
        if scored {
            guard #available(macOS 26.4, *),
                  await LanguageAvailability().status(from: Locale.Language(identifier: "en"), to: Locale.Language(identifier: "zh-Hans")) == .installed
            else { throw CocoaError(.featureUnsupported) }
            session = TranslationSession(installedSource: Locale.Language(identifier: "en"), target: Locale.Language(identifier: "zh-Hans"))
        }
        var automatic = 0, adjustable = 0, wrong = 0
        for sample in samples {
            let source = sample.text as NSString
            let expression = #"(?<!\w)"# + NSRegularExpression.escapedPattern(for: sample.phrase) + #"(?!\w)"#
            let pair = source.range(of: expression, options: .regularExpression)
            guard pair.location != NSNotFound else { throw CocoaError(.fileReadCorruptFile) }
            let hit = source.range(of: sample.word, options: .backwards, range: pair)
            guard hit.location != NSNotFound else { throw CocoaError(.fileReadCorruptFile) }
            let passage = try SentenceContext.passage(in: sample.text, selection: hit, language: "en")
            if passage.text == sample.phrase { automatic += 1; continue }
            if passage.text != sample.word { wrong += 1; print("unexpected-span", sample.id); continue }
            #if !WAX_CORPUS_BASELINE
            if let option = passage.phraseRangeChoices.first(where: { $0.text == sample.phrase }),
               let expanded = passage.selecting(option.range, anchor: passage.anchor),
               expanded.text == sample.phrase, expanded.anchor == passage.selection {
                adjustable += 1
                if let session {
                    let began = LookupTrace.now
                    var firstSentenceMs: Int?
                    #if WAX_PHRASE_PROGRESS
                    let result = try await LookupTranslation.translate(expanded, session: session, dictionary: [], onSentence: { _ in
                        firstSentenceMs = Int((LookupTrace.now - began) * 1000)
                    })
                    #else
                    let result = try await LookupTranslation.translate(expanded, session: session, dictionary: [])
                    #endif
                    var answer = ["id": sample.id, "phrase": sample.phrase, "gloss": result.meaning,
                                  "reference": result.wordReference ?? "", "origin": String(describing: result.origin),
                                  "sentence": result.sentenceTranslation ?? "",
                                  "latency_ms": String(Int((LookupTrace.now - began) * 1000))]
                    if let firstSentenceMs { answer["first_sentence_ms"] = String(firstSentenceMs) }
                    let line = try JSONEncoder().encode(answer)
                    print(String(decoding: line, as: UTF8.self))
                }
            } else { print("unavailable-range", sample.id) }
            #endif
        }
        print("total=\(samples.count) automatic=\(automatic) user_adjustable=\(adjustable) unexpected=\(wrong)")
    }
}
