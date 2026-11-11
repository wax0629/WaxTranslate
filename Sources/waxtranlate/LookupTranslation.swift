import CoreServices
import Foundation
import NaturalLanguage
import Translation

struct LookupResult {
    enum Origin { case sentence, dictionary, standalone, region, term, unresolved }
    let meaning: String
    let origin: Origin
    var sentenceTranslation: String? = nil
    var excerptTranslation: String? = nil
    var wordReference: String? = nil
    var isUsable: Bool { origin != .unresolved && !meaning.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }

    func canSave(for passage: Passage) -> Bool {
        guard isUsable else { return false }
        if passage.sourceLanguage == "en", passage.context != passage.text,
           LookupPolicy(passage).automaticallyTranslatesContext, !passage.context.isEmpty {
            return origin == .sentence || origin == .term
        }
        return true
    }

    static func initial(term: TermMeaning?, cached: LookupResult?, dictionary: [String]) -> LookupResult? {
        if let term {
            return LookupResult(meaning: TranslationOutput.normalize(term.meaning), origin: .term,
                                sentenceTranslation: cached?.origin == .term ? cached?.sentenceTranslation : nil,
                                excerptTranslation: cached?.origin == .term ? cached?.excerptTranslation : nil)
        }
        return cached ?? dictionary.first.map { LookupResult(meaning: $0, origin: .dictionary) }
    }
}

@MainActor final class LookupCache {
    static let shared = LookupCache()
    private struct Key: Hashable {
        let text: String, context: String, language: String
        let structure: Passage.Structure
        let extent: ContextExtent
        let selection: NSRange?, anchor: NSRange?
        init(_ passage: Passage) {
            text = passage.text; context = passage.context; language = passage.sourceLanguage
            selection = passage.selection; anchor = passage.anchor; structure = passage.structure; extent = passage.extent
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
        guard result.canSave(for: passage), passage.text.count <= 1000, passage.context.count <= 4000 else { return }
        guard passage.hasCompleteContext || result.origin != .sentence else { return }
        if SentenceExcerpt(passage).isTruncated && (result.sentenceTranslation == nil || result.excerptTranslation == nil) { return }
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
        // The hyphenated common noun is distinct from Apple's VoiceOver name.
        // Keep a complete local reference if the system dictionary exposes an
        // adjectival fragment before its ordinary noun sense.
        if passage.text.lowercased() == "voice-over" { return ["画外音", "旁白"] }
        let source = passage.context as CFString
        let selected = CFRange(location: selection.location, length: selection.length)
        guard let entry = DCSCopyTextDefinition(nil, source, selected)?.takeRetainedValue() else { return [] }
        let tagger = NLTagger(tagSchemes: [.lexicalClass])
        tagger.string = passage.context
        let part = tagger.tag(at: range.lowerBound, unit: .word, scheme: .lexicalClass).0
        return meanings(in: entry as String, partOfSpeech: part?.rawValue.lowercased())
    }

    // A mixed Chinese sentence has a different translation direction from its
    // English headword. Keep this as an explicitly independent reference.
    static func mixedEnglishReference(for passage: Passage) -> String? {
        guard (passage.sourceLanguage.hasPrefix("zh") || passage.sourceLanguage == "en"), !passage.isPhrase,
              let selection = passage.selection, let range = Range(selection, in: passage.context),
              passage.context[range] == passage.text,
              passage.text.range(of: #"^[A-Za-z]+$"#, options: .regularExpression) != nil else { return nil }
        func definition(_ word: String) -> String? {
            let word = word.lowercased()
            return candidates(for: Passage(text: word, context: word, language: "en"), language: "en").first
        }
        if let meaning = definition(passage.text) { return meaning }
        let separated = passage.text
            .replacingOccurrences(of: #"([A-Z]+)([A-Z][a-z])"#, with: "$1 $2", options: .regularExpression)
            .replacingOccurrences(of: #"([a-z])([A-Z])"#, with: "$1 $2", options: .regularExpression)
        let words = separated.split(separator: " ").map(String.init)
        guard words.count > 1 else { return nil }
        let meanings = words.compactMap { word in definition(word).map { word + "：" + $0 } }
        guard meanings.count == words.count else { return nil }
        return "名称组成词参考（不代表代码功能）：" + meanings.joined(separator: "；")
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
    struct Response {
        let text: String
        let attributed: AttributedString?
    }
    struct Provider {
        let plain: (String) async throws -> String
        let marked: ((AttributedString) async throws -> Response)?
    }

    static func makeResult(for passage: Passage, meaning: String, origin: LookupResult.Origin, sentence: String? = nil) -> LookupResult {
        let target = LookupPolicy(passage).headwordLanguage.hasPrefix("zh") ? "en" : "zh-Hans"
        let trim = CharacterSet.whitespacesAndNewlines.union(.punctuationCharacters)
        let gloss = meaning.trimmingCharacters(in: trim)
        let word = passage.text.precomposedStringWithCompatibilityMapping
        let latin = word.range(of: #"^[\p{Latin}\p{N}\s.+#’'_-]+$"#, options: .regularExpression) != nil &&
            word.range(of: #"\p{Latin}"#, options: .regularExpression) != nil
        // Shared Han spellings (e.g. Japanese 猫 → Chinese 猫) are valid.
        let unchanged = origin != .region && latin && gloss.caseInsensitiveCompare(passage.text.trimmingCharacters(in: trim)) == .orderedSame
        if unchanged, let reference = CompactGloss.mixedEnglishReference(for: passage) {
            return LookupResult(meaning: reference, origin: .dictionary,
                                sentenceTranslation: sentence.map { TranslationOutput.normalize($0, target: target) })
        }
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

    static func alignedMeaning(in output: AttributedString, isPhrase: Bool = false, passage: Passage? = nil) -> String? {
        // Accept only one contiguous translated span. Some language pairs may
        // drop the emphasis or apply it to the whole sentence.
        var span: Range<AttributedString.Index>?
        for run in output.runs where run.inlinePresentationIntent?.contains(.stronglyEmphasized) == true {
            if let previous = span, previous.upperBound != run.range.lowerBound { return nil }
            span = (span?.lowerBound ?? run.range.lowerBound)..<run.range.upperBound
        }
        guard let span else { return nil }
        let trim = CharacterSet.whitespacesAndNewlines.union(.punctuationCharacters)
        let plain = String(output.characters)
        let prefix = String(output[..<span.lowerBound].characters).utf16.count
        let range = NSRange(location: prefix, length: String(output[span].characters).utf16.count)
        let completed = ContextWordAlignment.completeTargetWord(range, in: plain, compoundHead: passage.map(ContextWordAlignment.isCompoundNounHead) ?? false)
        guard let selected = Range(completed, in: plain) else { return nil }
        let gloss = String(plain[selected]).trimmingCharacters(in: trim)
        let sentence = plain.trimmingCharacters(in: trim)
        guard !gloss.isEmpty, gloss.count <= 40, gloss != sentence else { return nil }
        // For the supported verb phrases these fragments omit the verb itself.
        if isPhrase && ["了", "的", "着", "过", "一下"].contains(gloss) { return nil }
        return gloss
    }

    private static let boundaryWords: Set<String> = ["的", "地", "得", "了", "着", "过", "中", "里", "上", "下", "内", "外", "在", "于", "从", "向", "到", "对", "与", "和"]

    private static func glossWords(_ gloss: String) -> [Range<String.Index>] {
        let tokenizer = NLTokenizer(unit: .word)
        tokenizer.string = gloss
        tokenizer.setLanguage(.simplifiedChinese)
        return tokenizer.tokens(for: gloss.startIndex..<gloss.endIndex)
    }

    static func needsBoundaryVerification(_ gloss: String) -> Bool {
        let words = glossWords(gloss)
        guard let first = words.first, let last = words.last else { return false }
        return boundaryWords.contains(String(gloss[first])) || boundaryWords.contains(String(gloss[last]))
    }

    static func verifiedBoundaryMeaning(_ gloss: String, references: [String]) -> String? {
        let gloss = TranslationOutput.normalize(gloss)
        let words = glossWords(gloss)
        for reference in references {
            let candidate = TranslationOutput.normalize(reference).trimmingCharacters(in: .whitespacesAndNewlines.union(.punctuationCharacters))
            guard !candidate.isEmpty else { continue }
            if candidate == gloss { return gloss }
            guard let core = gloss.range(of: candidate),
                  words.contains(where: { $0.lowerBound == core.lowerBound }),
                  words.contains(where: { $0.upperBound == core.upperBound }) else { continue }
            let outside = words.filter { $0.upperBound <= core.lowerBound || $0.lowerBound >= core.upperBound }
            // Never trim characters by suffix alone: the independent word gloss
            // must match a complete token span, with only function words outside.
            if !outside.isEmpty && outside.allSatisfy({ boundaryWords.contains(String(gloss[$0])) }) { return candidate }
        }
        return nil
    }

    static func translate(_ passage: Passage, session: TranslationSession, dictionary: [String], trace: LookupTrace = LookupTrace()) async throws -> LookupResult {
        let marked: ((AttributedString) async throws -> Response)?
        if #available(macOS 26.4, *) {
            marked = { value in
                let response = try await session.translate(value)
                return Response(text: response.targetText, attributed: response.attributedTargetText)
            }
        } else { marked = nil }
        return try await translate(passage, provider: Provider(plain: { try await session.translate($0).targetText }, marked: marked), dictionary: dictionary, trace: trace)
    }

    static func translate(_ passage: Passage, provider: Provider, dictionary: [String], trace: LookupTrace = LookupTrace()) async throws -> LookupResult {
        try Task.checkCancellation()
        // Enforce completeness at the provider boundary as well as in the card.
        // Explicit fragment translation uses TranslationRunner with a labelled,
        // user-selected source; automatic lookup only returns a word reference.
        if !passage.hasCompleteContext && !passage.context.isEmpty {
            if let term = LocalTerminology.lookup(passage) { return LookupResult(meaning: term.meaning, origin: .term) }
            let reference = try await provider.plain(passage.text)
            try Task.checkCancellation()
            return makeResult(for: passage, meaning: reference, origin: .standalone)
        }
        let excerpt = SentenceExcerpt(passage)
        var output: LookupResult
        if let term = LocalTerminology.lookup(passage), !passage.context.isEmpty, passage.context != passage.text {
            let began = LookupTrace.now
            let sentence = try await provider.plain(excerpt.passage.context)
            trace.record("translation.term_sentence", since: began)
            output = LookupResult(meaning: TranslationOutput.normalize(term.meaning), origin: .term,
                                  sentenceTranslation: TranslationOutput.normalize(sentence, target: passage.sourceLanguage.hasPrefix("zh") ? "en" : "zh-Hans"))
        } else {
            output = try await translateMeaning(excerpt.passage, retry: SentenceExcerpt.alignmentRetry(passage), provider: provider, dictionary: dictionary, trace: trace)
        }
        try Task.checkCancellation()
        if excerpt.isTruncated {
            output.excerptTranslation = output.sentenceTranslation
            output.sentenceTranslation = nil
            let began = LookupTrace.now
            do {
                let translated = try await provider.plain(passage.context)
                output.sentenceTranslation = TranslationOutput.normalize(translated, target: passage.sourceLanguage.hasPrefix("zh") ? "en" : "zh-Hans")
            } catch { try Task.checkCancellation() } // An optional full sentence must not erase the usable excerpt.
            try Task.checkCancellation()
            trace.record("translation.full_context", since: began)
        }
        // Recovery uses the whole original passage, retaining conditions and
        // the exact occurrence even when the card shows a shorter excerpt.
        if output.origin == .unresolved, let sentence = output.sentenceTranslation,
           let alignment = ContextWordAlignment(passage, translation: sentence, focus: .nounHead) {
            let began = LookupTrace.now
            if let recovered = try await alignment.recover(using: provider.plain) {
                let references = dictionary + [output.wordReference].compactMap { $0 }
                let gloss = needsBoundaryVerification(recovered) && !passage.isPhrase
                    ? verifiedBoundaryMeaning(recovered, references: references) : recovered
                if let gloss, !passage.isPhrase || !["了", "的", "着", "过", "一下"].contains(gloss) {
                    output = LookupResult(meaning: gloss, origin: .sentence, sentenceTranslation: sentence,
                                          excerptTranslation: output.excerptTranslation)
                }
            }
            try Task.checkCancellation()
            trace.record("translation.context_word_recovery", since: began)
        }
        return output
    }

    private static func translateMeaning(_ passage: Passage, retry: Passage?, provider: Provider, dictionary: [String], trace: LookupTrace) async throws -> LookupResult {
        func result(_ meaning: String, _ origin: LookupResult.Origin, _ sentence: String? = nil) -> LookupResult {
            makeResult(for: passage, meaning: meaning, origin: origin, sentence: sentence)
        }
        guard !passage.context.isEmpty, passage.context != passage.text else {
            let began = LookupTrace.now
            let text = try await provider.plain(passage.text)
            trace.record("translation.word_or_region", since: began)
            return result(text, passage.context.isEmpty ? .region : .standalone)
        }

        let sentence: String
        var alignedGloss: String?
        let sentenceBegan = LookupTrace.now
        if let translateMarked = provider.marked, let marked = markedSentence(passage),
           let response = try? await translateMarked(marked) {
            try Task.checkCancellation()
            sentence = response.text
            trace.record("translation.aligned_sentence", since: sentenceBegan)
            alignedGloss = response.attributed.flatMap { alignedMeaning(in: $0, isPhrase: passage.isPhrase, passage: passage) }
        } else {
            try Task.checkCancellation()
            sentence = try await provider.plain(passage.context)
            trace.record("translation.plain_sentence", since: sentenceBegan)
        }

        if let gloss = alignedGloss {
            if passage.sourceLanguage.hasPrefix("zh") || passage.isPhrase || !needsBoundaryVerification(gloss) { return result(gloss, .sentence, sentence) }
            if let verified = verifiedBoundaryMeaning(gloss, references: dictionary) { return result(verified, .sentence, sentence) }
        }

        // One bounded retry, retaining the exact occurrence and the original
        // sentence translation. Never accept a dictionary substring elsewhere
        // in the translation as evidence for the selected word.
        if let retry, retry.context != passage.context, let marked = markedSentence(retry), let translateMarked = provider.marked {
            let began = LookupTrace.now
            if let response = try? await translateMarked(marked), let attributed = response.attributed,
               let gloss = alignedMeaning(in: attributed, isPhrase: passage.isPhrase, passage: retry) {
                try Task.checkCancellation()
                if passage.isPhrase || !needsBoundaryVerification(gloss) { return result(gloss, .sentence, sentence) }
                if let verified = verifiedBoundaryMeaning(gloss, references: dictionary) { return result(verified, .sentence, sentence) }
                alignedGloss = gloss
            }
            try Task.checkCancellation()
            trace.record("translation.alignment_retry", since: began)
        }

        func referenceResult(_ meaning: String, origin: LookupResult.Origin) -> LookupResult {
            let reference = result(meaning, origin, sentence)
            guard passage.sourceLanguage == "en", passage.hasCompleteContext, reference.isUsable else { return reference }
            // A successful sentence translation does not confirm the standalone
            // word's sense. Keep it as a secondary reference, out of saves/cache.
            return LookupResult(meaning: "", origin: .unresolved, sentenceTranslation: reference.sentenceTranslation,
                                wordReference: reference.meaning)
        }

        // A dictionary gloss elsewhere in the sentence may translate a different word.
        do {
            try Task.checkCancellation()
            let wordBegan = LookupTrace.now
            let reference = try await provider.plain(passage.text)
            trace.record("translation.fallback_word", since: wordBegan)
            if let alignedGloss, let verified = verifiedBoundaryMeaning(alignedGloss, references: [reference]) {
                return result(verified, .sentence, sentence)
            }
            return referenceResult(reference, origin: .standalone)
        } catch {
            try Task.checkCancellation()
            guard let reference = dictionary.first else { throw error }
            return referenceResult(reference, origin: .dictionary)
        }
    }
}
