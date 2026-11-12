import Foundation
import Translation

#if LONG_CONTEXT_STANDALONE
@main @MainActor struct LongContextMain {
    static func main() async {
        do { try await LongContextTests.run() }
        catch { FileHandle.standardError.write(Data("Long-context regression failed: \(error)\n".utf8)); exit(1) }
    }
}
#endif

@MainActor enum LongContextTests {
    struct Failure: Error, CustomStringConvertible {
        let description: String
    }
    static func check(_ condition: Bool, _ description: String) throws {
        if !condition { throw Failure(description: description) }
    }
    static let river = "After a very long walk through the quiet village and past the old houses where people were preparing for the evening, they sat on the river bank and watched the water flow slowly toward the distant mountains."
    static let money = "After a long meeting with her colleagues and several delays on the way through the crowded city, she deposited her paycheck at the bank before she drove home to make dinner."
    static let repeated = "After they had visited the bank to deposit their savings, they walked along the river bank before returning to the village for dinner."

    static func run() async throws {
        try compoundBoundaries()
        try await recordedOutputs()
        try await failureBoundaries()
        try await providerAndPersistence()
        try await progressiveMeaning()
        try await installed()
    }

    private static func compoundBoundaries() throws {
        let source = "They rested beside the river bank."
        let noun = Passage(text: "bank", context: source, language: "en")
        let modifier = Passage(text: "river", context: source, language: "en")
        func marked(_ sentence: String, _ gloss: String) -> AttributedString {
            var result = AttributedString(sentence)
            let range = Range((sentence as NSString).range(of: gloss), in: result)!
            result[range].inlinePresentationIntent = .stronglyEmphasized
            return result
        }
        try check(LookupTranslation.alignedMeaning(in: marked("他们在河岸边休息。", "边"), passage: noun) == "河岸边", "noun head was clipped to a single suffix")
        try check(LookupTranslation.alignedMeaning(in: marked("他们在河边休息。", "河"), passage: modifier) == "河", "modifier was expanded into its head noun")
        let barkSource = "They examined the tree bark before leaving."
        try check(LookupTranslation.alignedMeaning(in: marked("他们检查了树皮。", "皮"), passage: Passage(text: "bark", context: barkSource, language: "en")) == "树皮", "compound completion only worked for bank")
        try check(!ContextWordAlignment.isCompoundNounHead(Passage(text: "bank", context: "They watched the river\n\nbank.", language: "en")), "compound crossed a paragraph boundary")
        print("Compound target boundaries: complete noun heads, preserve modifiers, non-bank words and paragraph guard passed.")
    }

    private static func recordedOutputs() async throws {
        struct Corpus: Decodable {
            struct Case: Decodable { let id: String; let word: String; let source: String; let last: Bool; let translation: String; let responses: [String]; let expected: [String] }
            let cases: [Case]
        }
        let corpus = try JSONDecoder().decode(Corpus.self, from: Data(contentsOf: URL(fileURLWithPath: "Tests/Fixtures/context-word-alignment.json")))
        var failures: [String] = []
        for sample in corpus.cases {
            let selection = (sample.source as NSString).range(of: sample.word, options: sample.last ? .backwards : [])
            let passage = Passage(text: sample.word, context: sample.source, selection: selection, language: "en")
            guard let alignment = ContextWordAlignment(passage, translation: sample.translation) else { throw Failure(description: sample.id + ": no alignment request") }
            let replacements = ["<b>\(sample.word)</b>", "<i>\(sample.word)</i>", "\"\(sample.word)\""]
            let requests = replacements.map { (sample.source as NSString).replacingCharacters(in: selection, with: $0) }
            var count = 0
            let meaning = try await alignment.recover { request in
                try check(count < 3 && request == requests[count], sample.id + ": marked the wrong source occurrence")
                defer { count += 1 }
                return sample.responses[count]
            }
            let correct = sample.expected.isEmpty ? meaning == nil : sample.expected.contains(meaning ?? "")
            print("Recorded recovery →", sample.id, meaning ?? "unconfirmed")
            if !correct { failures.append("\(sample.id): expected \(sample.expected), got \(meaning ?? "unconfirmed")") }
            try check(count <= 3, sample.id + ": unbounded requests")
        }
        try check(failures.isEmpty, failures.joined(separator: "; "))
        print("Recorded alignment outputs:", corpus.cases.count, "passed (including synonyms, copied source tokens, object exclusion and rejected evidence).")
    }

    private static func failureBoundaries() async throws {
        let source = "They visited the bank, then sat on the river bank and watched the water."
        let passage = Passage(text: "bank", context: source, selection: (source as NSString).range(of: "bank", options: .backwards), language: "en")
        let target = "他们去了银行，然后坐在河岸上看水。"
        let alignment = ContextWordAlignment(passage, translation: target)!
        let cases: [(String, [String])] = [
            ("lost markers", [target, target]),
            ("duplicate markers", ["他们坐在<b>岸</b>边和<b>岸</b>上。", "他们坐在<i>岸</i>边和<i>岸</i>上。"]),
            ("empty markers", ["他们去了银行，然后坐在河<b></b>上看水。", "他们去了银行，然后坐在河<i></i>上看水。"]),
            ("conflicting locations", ["他们去了<b>银行</b>，然后坐在河岸上看水。", "他们去了银行，然后坐在河<i>岸</i>上看水。"]),
            ("wrong sense elsewhere", ["他们去了银行，然后坐在河<b>银行</b>上看水。", "他们去了银行，然后坐在河<i>银行</i>上看水。"]),
            ("unrelated output", ["今天的天气<b>银行</b>很好。", "今天的天气<i>银行</i>很好。"])
        ]
        for (name, responses) in cases {
            var calls = 0
            let meaning = try await alignment.recover { _ in
                defer { calls += 1 }
                return responses[min(calls, responses.count - 1)]
            }
            try check(meaning == nil, name + ": accepted an unrelated meaning")
            try check(calls <= 3, name + ": exceeded the bounded request count")
        }
        try check(ContextWordAlignment(Passage(text: "bank", context: source, selection: NSRange(location: 0, length: 3), language: "en"), translation: target) == nil, "stale source selection accepted")
        try check(ContextWordAlignment(Passage(text: "bank", context: source, language: "en", extent: .missingStart), translation: target) == nil, "incomplete source accepted")
        try check(ContextWordAlignment(Passage(text: "bank", context: source, language: "en", structure: .code), translation: target) == nil, "code accepted")
        try check(ContextWordAlignment(Passage(text: "bank", context: source + " <b>literal</b>", language: "en"), translation: target) == nil, "original markup collided with a probe")
        try check(ContextWordAlignment(Passage(text: "bank", context: source, language: "fr"), translation: target) == nil, "foreign direction changed")
        try check(ContextWordAlignment(passage, translation: "") == nil, "empty translation accepted")
        var failures = 0
        let failed = try await alignment.recover { _ in failures += 1; throw Failure(description: "model unavailable") }
        try check(failed == nil && failures == 1, "service failure retried or became a meaning")
        let duplicate = ContextWordAlignment(Passage(text: "bank", context: "They visited the bank, then visited the bank again.", language: "en"), translation: "他们参观银行，然后参观银行。")!
        let omitted = try await duplicate.recover { input in
            input.contains("<b>") ? "他们参观<b>银行</b>。" : "他们参观<i>银行</i>。"
        }
        try check(omitted == nil, "probe omitted a repeated clause but guessed an occurrence")
        let cancelled = Task {
            try await alignment.recover { _ in
                withUnsafeCurrentTask { $0?.cancel() }
                return "他们去了银行，然后坐在河<b>岸</b>上看水。"
            }
        }
        do { _ = try await cancelled.value; throw Failure(description: "recovery swallowed cancellation") }
        catch is CancellationError { }
        print("Alignment failure boundaries: 6 malformed/conflicting outputs, selection/structure/language guards, service failure and cancellation passed.")
    }

    private static func providerAndPersistence() async throws {
        let text = "📚 After visiting the bank, they sat on the river bank and watched the water."
        let passage = Passage(text: "bank", context: text, selection: (text as NSString).range(of: "bank", options: .backwards), language: "en")
        let sentence = "他们去了银行，然后坐在河岸上看水。"
        var probes = 0
        let provider = LookupTranslation.Provider(plain: { input in
            if input.contains("<b>") {
                probes += 1
                try check(input == "📚 After visiting the bank, they sat on the <b>river bank</b> and watched the water.", "UTF-16 source occurrence changed")
                return "他们去了银行，然后坐在河<b>岸</b>上看水。"
            }
            if input.contains("<i>") { probes += 1; return "他们去了银行，然后坐在河<i>岸</i>上看水。" }
            return input == "bank" ? "银行" : sentence
        }, marked: nil)
        let result = try await LookupTranslation.translate(passage, provider: provider, dictionary: ["银行"])
        try check(result.origin == .sentence && result.meaning == "河岸" && result.wordReference == nil && probes == 2, "plain provider did not recover the selected word")
        try check(result.sentenceTranslation == sentence && result.canSave(for: passage), "original translation/saveability changed")
        let cache = LookupCache()
        cache.insert(result, for: passage)
        try check(cache.result(for: passage)?.meaning == "河岸", "recovered result was not cached")
        let first = Passage(text: "bank", context: text, selection: (text as NSString).range(of: "bank"), language: "en")
        try check(cache.result(for: first) == nil, "recovered cache leaked to another occurrence")
        let suite = "WaxTranslate.Test.long-context." + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let book = Notebook(defaults: defaults)
        try check(book.recordLookup(passage, meaning: result.meaning) != nil, "recovered lookup was not recorded")
        try check(book.save(passage, translation: result.meaning, sentenceTranslation: result.sentenceTranslation, origin: "sentence"), "recovered lookup could not be saved")
        let loaded = Notebook(defaults: defaults)
        try check(loaded.entries.count == 1 && loaded.entries[0].source == "bank" && loaded.entries[0].target == "河岸" && loaded.entries[0].passage.selection == passage.selection && loaded.entries[0].context == text, "reloaded word lost original context or exact occurrence")
        try check(loaded.entries[0].sentenceTranslation == sentence && loaded.totalLookups == 1, "reloaded translation/count changed")
        print("Plain-provider recovery: UTF-16 occurrence, 2-probe budget, original translation, cache isolation, save and reload passed.")
    }

    private static func progressiveMeaning() async throws {
        let passage = Passage(text: "bank", context: river, language: "en")
        try check(SentenceExcerpt(passage).isTruncated, "fixture requires a separate full translation")
        var events: [String] = []
        func dictionary() -> [String] { events.append("dictionary"); return ["银行"] }
        let provider = LookupTranslation.Provider(plain: { text in
            try check(text == river, "unexpected extra model request")
            events.append("full")
            return "他们坐在河岸上看水。"
        }, marked: { _ in
            var gloss = AttributedString("河岸")
            gloss.inlinePresentationIntent = .stronglyEmphasized
            return .init(text: "他们坐在河岸。", attributed: AttributedString("他们坐在") + gloss + AttributedString("。"))
        })
        let result = try await LookupTranslation.translate(passage, provider: provider, dictionary: dictionary()) { excerpt in
            events.append(excerpt.meaning)
            if excerpt.sentenceTranslation != nil || excerpt.excerptTranslation == nil { events.append("wrong excerpt") }
        }
        try check(events == ["河岸", "full"] && result.sentenceTranslation == "他们坐在河岸上看水。",
                  "confirmed sense must precede full translation and avoid waiting for the dictionary")
        print("Confirmed excerpt appeared before the full sentence; unambiguous alignment bypassed dictionary waiting.")
    }

    private static func installed() async throws {
        let source = Locale.Language(identifier: "en"), target = Locale.Language(identifier: "zh-Hans")
        guard #available(macOS 26.0, *), await LanguageAvailability().status(from: source, to: target) == .installed else {
            print("Skipping live long-context checks: requires macOS 26+ with installed EN/ZH; deterministic checks remain independent.")
            return
        }
        let session = TranslationSession(installedSource: source, target: target)
        let cases: [(String, String, String, Bool, [String])] = [
            ("long-river", "bank", river, false, ["岸", "河岸", "岸边", "河岸边"]),
            ("long-money", "bank", money, false, ["银行"]),
            ("repeated-first", "bank", repeated, false, ["银行"]),
            ("repeated-last", "bank", repeated, true, ["岸", "河岸", "岸边", "河岸边"]),
            ("emoji-offset", "bank", "📚 " + river, false, ["岸", "河岸", "岸边", "河岸边"]),
            ("sentence-start", "Bank", "Bank customers who had waited outside the building for most of the morning were finally able to deposit their savings after the doors opened.", false, ["银行"]),
            ("sentence-end", "bank", "After leaving the quiet village and following the winding path through the forest for most of the afternoon, the tired travelers finally rested beside the river bank.", false, ["岸", "河岸", "岸边", "河岸边", "河边"]),
            ("negative-river", "bank", "Although they did not want to get wet after the heavy rain earlier in the afternoon, they sat on the river bank and watched the water.", false, ["岸", "河岸", "岸边", "河岸边"]),
            ("conditional-river", "bank", "If the weather remains calm after the long walk through the village and the old forest, they will rest on the river bank and watch the water.", false, ["岸", "河岸", "岸边", "河岸边"]),
            ("contrast-two-senses", "bank", "They did not visit the financial bank, but instead rested on the river bank while the children watched the water.", true, ["岸", "河岸", "岸边", "河岸边"]),
            ("tree-bark", "bark", "After walking through the forest for several hours, the botanist carefully examined the bark of the old tree before recording her observations.", false, ["树皮"]),
            ("dog-bark", "bark", "Although the little dog had been quiet for most of the afternoon, its loud bark woke everyone who was sleeping in the house.", false, ["叫声", "吠声", "吠叫"]),
            ("lifting-crane", "crane", "After inspecting the construction site and checking every safety cable, the operator used the crane to lift the heavy steel beam into position.", false, ["起重机"]),
            ("bird-crane", "crane", "After walking through the wetland in the early morning, the photographer watched a crane spread its wings and fly over the water.", false, ["鹤", "仙鹤"]),
            ("charging-battery", "charge", "After checking the cable and cleaning the connector, she decided to charge the battery before leaving for the long journey.", false, ["充电"]),
            ("negative-phrase", "rule out", "After carefully examining the patient's condition and reviewing the history of the illness, these results do not rule out infection and further testing is still required.", false, ["排除"])
        ]
        for (name, word, text, last, expected) in cases {
            let passage = Passage(text: word, context: text, selection: (text as NSString).range(of: word, options: last ? .backwards : []),
                                  anchor: word == "rule out" ? (text as NSString).range(of: "out") : nil, language: "en")
            let began = LookupTrace.now
            let result = try await LookupTranslation.translate(passage, session: session, dictionary: [])
            try check(result.origin == .sentence && expected.contains(result.meaning), "\(name): expected contextual \(expected), got \(result.origin) / \(result.meaning)")
            try check(result.sentenceTranslation != nil && result.canSave(for: passage), "\(name): full translation or saveability lost")
            print("Live long-context →", name, result.meaning, String(format: "%.0f ms", (LookupTrace.now - began) * 1000))
        }
        let plainOnly = LookupTranslation.Provider(plain: { try await session.translate($0).targetText }, marked: nil)
        let restored = try await LookupTranslation.translate(Passage(text: "bank", context: river, language: "en"), provider: plainOnly, dictionary: [])
        try check(restored.origin == .sentence && ["岸", "河岸", "岸边", "河岸边"].contains(restored.meaning), "plain-only live provider could not recover the river sense")
        print("Live long-context: \(cases.count) queries plus a plain-only provider passed; no unresolved result counts as success.")
    }
}
