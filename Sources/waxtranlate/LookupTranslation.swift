import CoreServices
import Foundation
import NaturalLanguage
import Translation

struct LookupResult {
    enum Origin { case sentence, dictionary, standalone, region, term, unresolved }
    let meaning: String
    let origin: Origin
    var sentenceTranslation: String? = nil
    var isUsable: Bool { origin != .unresolved && !meaning.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }

    static func initial(term: TermMeaning?, cached: LookupResult?, dictionary: [String]) -> LookupResult? {
        if let term {
            return LookupResult(meaning: TranslationOutput.normalize(term.meaning), origin: .term,
                                sentenceTranslation: cached?.origin == .term ? cached?.sentenceTranslation : nil)
        }
        return cached ?? dictionary.first.map { LookupResult(meaning: $0, origin: .dictionary) }
    }
}

@MainActor final class LookupCache {
    static let shared = LookupCache()
    private struct Key: Hashable {
        let text: String, context: String, language: String
        let selection: NSRange?, anchor: NSRange?
        init(_ passage: Passage) {
            text = passage.text; context = passage.context; language = passage.sourceLanguage
            selection = passage.selection; anchor = passage.anchor
        }
    }
    private var entries: [Key: (LookupResult, Date)] = [:]
    private var order: [Key] = []
    private let capacity: Int
    init(capacity: Int = 64) { self.capacity = max(1, capacity) }
    func result(for passage: Passage, now: Date = Date()) -> LookupResult? {
        let key = Key(passage)
        guard let (value, expires) = entries[key] else { return nil }
        guard expires > now else { entries[key] = nil; order.removeAll { $0 == key }; return nil }
        order.removeAll { $0 == key }; order.append(key)
        return value
    }
    func insert(_ result: LookupResult, for passage: Passage, now: Date = Date()) {
        guard result.isUsable, passage.text.count <= 1000, passage.context.count <= 4000 else { return }
        let key = Key(passage)
        entries[key] = (result, now.addingTimeInterval(600))
        order.removeAll { $0 == key }; order.append(key)
        while order.count > capacity { entries[order.removeFirst()] = nil }
    }
}

@MainActor enum TranslationWarmup {
    private static var task: Task<Void, Never>?
    static func start() {
        guard #available(macOS 26.0, *), task == nil else { return }
        task = Task {
            let source = Locale.Language(identifier: "en"), target = Locale.Language(identifier: "zh-Hans")
            guard await LanguageAvailability().status(from: source, to: target) == .installed else { return }
            let session = TranslationSession(installedSource: source, target: target)
            // Fixed local sample only. Never download a pack or submit user text.
            _ = try? await session.translate("Hello.")
        }
    }
}

enum CompactGloss {
    static func candidates(for passage: Passage, language: String) -> [String] {
        // Dictionary Services can return an entry for just one word of a phrase.
        guard language == "en", !passage.isPhrase, let selection = passage.selection,
              let range = Range(selection, in: passage.context) else { return [] }
        let source = passage.context as CFString
        let selected = CFRange(location: selection.location, length: selection.length)
        guard let entry = DCSCopyTextDefinition(nil, source, selected)?.takeRetainedValue() else { return [] }
        let tagger = NLTagger(tagSchemes: [.lexicalClass])
        tagger.string = passage.context
        let part = tagger.tag(at: range.lowerBound, unit: .word, scheme: .lexicalClass).0
        return meanings(in: entry as String, partOfSpeech: part?.rawValue.lowercased())
    }

    static func meanings(in entry: String, partOfSpeech: String? = nil) -> [String] {
        // Some installed dictionaries interpret English strings as Chinese pinyin.
        guard entry.range(of: #"^[A-Za-z]"#, options: .regularExpression) != nil else { return [] }
        let body = entry.components(separatedBy: " | ").last ?? entry
        let sections = body.components(separatedBy: sectionMarkers)
        let preferred = sections.filter { section in
            guard let partOfSpeech else { return false }
            return section.range(of: #"^(?:transitive |intransitive |auxiliary |modal )?"# + partOfSpeech + #"\b"#,
                                 options: [.regularExpression, .caseInsensitive]) != nil
        }
        var result: [String] = []
        for section in preferred + sections {
            for sense in section.components(separatedBy: senseMarkers) {
                let definition = sense.components(separatedBy: "▸")[0]
                for variant in definition.components(separatedBy: ";") {
                    guard let span = variant.range(of: #"[\p{Han}]+(?:[…·]+[\p{Han}]+)*"#, options: .regularExpression) else { continue }
                    let gloss = TranslationOutput.normalize(String(variant[span]))
                    if gloss.count <= 32 && !result.contains(gloss) { result.append(gloss) }
                }
            }
        }
        return result
    }

    private static let sectionMarkers = try! NSRegularExpression(pattern: #"(?:^|\s)[A-Z]\.\s+(?=[a-z])"#)
    private static let senseMarkers = CharacterSet(charactersIn: "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳")
}

private extension String {
    func components(separatedBy regex: NSRegularExpression) -> [String] {
        let range = NSRange(startIndex..<endIndex, in: self)
        return regex.stringByReplacingMatches(in: self, range: range, withTemplate: "\u{1f}").components(separatedBy: "\u{1f}")
    }
}

enum LookupTranslation {
    static func makeResult(for passage: Passage, meaning: String, origin: LookupResult.Origin, sentence: String? = nil) -> LookupResult {
        let target = passage.sourceLanguage.hasPrefix("zh") ? "en" : "zh-Hans"
        let trim = CharacterSet.whitespacesAndNewlines.union(.punctuationCharacters)
        let gloss = meaning.trimmingCharacters(in: trim)
        let word = passage.text.precomposedStringWithCompatibilityMapping
        let latin = word.range(of: #"^[\p{Latin}\p{N}\s.+#’'_-]+$"#, options: .regularExpression) != nil &&
            word.range(of: #"\p{Latin}"#, options: .regularExpression) != nil
        // Shared Han spellings (e.g. Japanese 猫 → Chinese 猫) are valid.
        let unchanged = origin != .region && latin && gloss.caseInsensitiveCompare(passage.text.trimmingCharacters(in: trim)) == .orderedSame
        return LookupResult(meaning: unchanged || gloss.isEmpty ? "" : TranslationOutput.normalize(meaning, target: target),
                            origin: unchanged || gloss.isEmpty ? .unresolved : origin,
                            sentenceTranslation: sentence.map { TranslationOutput.normalize($0, target: target) })
    }

    static func markedSentence(_ passage: Passage) -> AttributedString? {
        guard let selection = passage.selection, let range = Range(selection, in: passage.context),
              passage.context[range] == passage.text else { return nil }
        var mark = AttributedString(passage.context[range])
        mark.inlinePresentationIntent = .stronglyEmphasized
        return AttributedString(passage.context[..<range.lowerBound]) + mark + AttributedString(passage.context[range.upperBound...])
    }

    static func alignedMeaning(in output: AttributedString, isPhrase: Bool = false) -> String? {
        // Accept only one contiguous translated span. Some language pairs may
        // drop the emphasis or apply it to the whole sentence.
        var span: Range<AttributedString.Index>?
        for run in output.runs where run.inlinePresentationIntent?.contains(.stronglyEmphasized) == true {
            if let previous = span, previous.upperBound != run.range.lowerBound { return nil }
            span = (span?.lowerBound ?? run.range.lowerBound)..<run.range.upperBound
        }
        guard let span else { return nil }
        let trim = CharacterSet.whitespacesAndNewlines.union(.punctuationCharacters)
        var gloss = String(output[span].characters).trimmingCharacters(in: trim)
        let sentence = String(output.characters).trimmingCharacters(in: trim)
        guard !gloss.isEmpty, gloss.count <= 40, gloss != sentence else { return nil }
        // Apple can attach the preceding modifier particle to a Chinese adjective
        // (e.g. "的新"). Leave words such as "的确" intact.
        if gloss.first == "的" && gloss.count > 1 {
            let tokenizer = NLTokenizer(unit: .word)
            tokenizer.string = gloss
            tokenizer.setLanguage(.simplifiedChinese)
            let first = tokenizer.tokenRange(at: gloss.startIndex)
            if gloss[first] == "的" { gloss = String(gloss[first.upperBound...]).trimmingCharacters(in: .whitespaces) }
        }
        // For the supported verb phrases these fragments omit the verb itself.
        if isPhrase && ["了", "的", "着", "过", "一下"].contains(gloss) { return nil }
        return gloss
    }

    static func translate(_ passage: Passage, session: TranslationSession, dictionary: [String], trace: LookupTrace = LookupTrace()) async throws -> LookupResult {
        func result(_ meaning: String, _ origin: LookupResult.Origin, _ sentence: String? = nil) -> LookupResult {
            makeResult(for: passage, meaning: meaning, origin: origin, sentence: sentence)
        }
        guard !passage.context.isEmpty, passage.context != passage.text else {
            let began = LookupTrace.now
            let text = try await session.translate(passage.text).targetText
            trace.record("translation.word_or_region", since: began)
            return result(text, passage.context.isEmpty ? .region : .standalone)
        }

        let sentence: String
        let sentenceBegan = LookupTrace.now
        if #available(macOS 26.4, *), let marked = markedSentence(passage),
           let response = try? await session.translate(marked) {
            sentence = response.targetText
            trace.record("translation.aligned_sentence", since: sentenceBegan)
            if let formatted = response.attributedTargetText,
               let gloss = alignedMeaning(in: formatted, isPhrase: passage.isPhrase) {
                return result(gloss, .sentence, sentence)
            }
        } else {
            try Task.checkCancellation()
            sentence = try await session.translate(passage.context).targetText
            trace.record("translation.plain_sentence", since: sentenceBegan)
        }

        // A dictionary gloss elsewhere in the sentence may translate a different word.
        do {
            try Task.checkCancellation()
            let wordBegan = LookupTrace.now
            let reference = try await session.translate(passage.text).targetText
            trace.record("translation.fallback_word", since: wordBegan)
            return result(reference, .standalone, sentence)
        } catch {
            try Task.checkCancellation()
            guard let reference = dictionary.first else { throw error }
            return result(reference, .dictionary, sentence)
        }
    }
}
