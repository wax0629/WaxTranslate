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
            return origin == .sentence || origin == .term ||
                (origin == .standalone && passage.isPhrase && !SentenceContext.isPhrasalVerb(passage.text))
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

    static func initialReference(_ references: [String], for passage: Passage) -> LookupResult? {
        // A dictionary's first sense is not evidence for this occurrence. Keep
        // the main gloss and copy/save actions empty while context is resolving.
        guard passage.context == passage.text || !LookupPolicy(passage).automaticallyTranslatesContext else { return nil }
        return references.first.map { LookupResult(meaning: $0, origin: .dictionary) }
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
        task = Task.detached(priority: .utility) {
            let source = Locale.Language(identifier: "en"), target = Locale.Language(identifier: "zh-Hans")
            guard await LanguageAvailability().status(from: source, to: target) == .installed else { return }
            let session = TranslationSession(installedSource: source, target: target)
            // Fixed local sample only. Never download a pack or submit user text.
            let sample = Passage(text: "guide", context: "Read the user guide.", language: "en")
            if #available(macOS 26.4, *), let marked = LookupTranslation.markedSentence(sample) {
                _ = try? await session.translate(marked)
            } else { _ = try? await session.translate(sample.context) }
        }
    }
}

// Start an installed local model as soon as the source is known, while SwiftUI
// lays out the card. The card alone publishes/cache/saves results; abandoning a
// card cancels both the worker and its session. Download UI still uses SwiftUI.
final class AutomaticLookup: @unchecked Sendable {
    enum Progress { case sentence(String), excerpt(LookupResult) }
    let progress: AsyncStream<Progress>
    let task: Task<LookupResult?, Error>

    static func start(_ passage: Passage, trace: LookupTrace) -> AutomaticLookup? {
        guard #available(macOS 26.0, *) else { return nil }
        return AutomaticLookup(passage, trace: trace)
    }

    @available(macOS 26.0, *)
    private init(_ passage: Passage, trace: LookupTrace) {
        let (stream, continuation) = AsyncStream<Progress>.makeStream()
        progress = stream
        task = Task.detached(priority: .userInitiated) {
            defer { continuation.finish() }
            let began = LookupTrace.now
            let source = Locale.Language(identifier: passage.sourceLanguage)
            let target = Locale.Language(identifier: passage.sourceLanguage.hasPrefix("zh") ? "en" : "zh-Hans")
            try Task.checkCancellation()
            var references: [String]?
            func dictionary() async -> [String] {
                if let references { return references }
                let began = LookupTrace.now
                let values = await CompactGloss.references(for: passage)
                trace.record("lookup.dictionary", since: began)
                references = values
                return values
            }
            let session = TranslationSession(installedSource: source, target: target)
            trace.record("translation.session", since: began)
            do {
                return try await withTaskCancellationHandler {
                    try Task.checkCancellation()
                    let result = try await LookupTranslation.translate(passage, session: session, dictionary: await dictionary(),
                        trace: trace, onSentence: { continuation.yield(.sentence($0)) },
                        onExcerpt: { continuation.yield(.excerpt($0)) })
                    try Task.checkCancellation()
                    trace.record("lookup.ready", since: began)
                    return result
                } onCancel: { session.cancel() }
            // Installed-only sessions never download. Avoid a separate readiness
            // IPC on every lookup; a missing/unsupported pair returns to the UI.
            } catch TranslationError.notInstalled { return nil }
            catch TranslationError.unsupportedSourceLanguage { return nil }
            catch TranslationError.unsupportedTargetLanguage { return nil }
            catch TranslationError.unsupportedLanguagePairing { return nil }
        }
    }

    func cancel() { task.cancel() }
    deinit { task.cancel() }
}

enum CompactGloss {
    // Dictionary Services may load its data on the first word. Keep this work off the card's UI actor.
    static func references(for passage: Passage) async -> [String] {
        guard !Task.isCancelled else { return [] }
        var references = candidates(for: passage, language: passage.sourceLanguage)
        guard !Task.isCancelled else { return [] }
        if let independent = mixedEnglishReference(for: passage), !independent.hasPrefix("名称组成词参考") {
            references.append(independent)
        }
        return references
    }

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
        var batch: (([String]) async throws -> [String])? = nil
        var supportsContextLinks = false
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
        if let compound = ContextWordAlignment.nounHeadRange(passage) {
            var value = AttributedString(passage.context)
            if let whole = Range(compound, in: value), let selected = Range(selection, in: value) {
                value[whole].inlinePresentationIntent = .emphasized
                value[selected].inlinePresentationIntent = [.emphasized, .stronglyEmphasized]
                return value
            }
        }
        var mark = AttributedString(passage.context[range])
        mark.inlinePresentationIntent = .stronglyEmphasized
        return AttributedString(passage.context[..<range.lowerBound]) + mark + AttributedString(passage.context[range.upperBound...])
    }

    static func alignedMeaning(in output: AttributedString, isPhrase: Bool = false, passage: Passage? = nil, requiredLink: URL? = nil) -> String? {
        // Accept only one contiguous translated span. Some language pairs may
        // drop the emphasis or apply it to the whole sentence.
        var span: Range<AttributedString.Index>?
        let intent: InlinePresentationIntent = output.runs.contains(where: { $0.inlinePresentationIntent?.contains(.stronglyEmphasized) == true })
            ? .stronglyEmphasized : passage.flatMap(ContextWordAlignment.nounHeadRange) != nil ? .emphasized : .stronglyEmphasized
        for run in output.runs where run.inlinePresentationIntent?.contains(intent) == true {
            if let previous = span, previous.upperBound != run.range.lowerBound {
                return passage.flatMap { countedNounMeaning(in: output, passage: $0, requiredLink: requiredLink) }
            }
            span = (span?.lowerBound ?? run.range.lowerBound)..<run.range.upperBound
        }
        guard let span else { return nil }
        let trim = CharacterSet.whitespacesAndNewlines.union(.punctuationCharacters)
        let plain = String(output.characters)
        let prefix = String(output[..<span.lowerBound].characters).utf16.count
        let range = NSRange(location: prefix, length: String(output[span].characters).utf16.count)
        let completed = ContextWordAlignment.completeTargetWord(range, in: plain, compoundHead: passage.map(ContextWordAlignment.isCompoundNounHead) ?? false)
        if let requiredLink {
            guard let attributedRange = Range(completed, in: output),
                  output[attributedRange].runs.allSatisfy({ $0.link == requiredLink }) else { return nil }
        }
        guard let selected = Range(completed, in: plain) else { return nil }
        let gloss = String(plain[selected]).trimmingCharacters(in: trim)
        let sentence = plain.trimmingCharacters(in: trim)
        guard !gloss.isEmpty, gloss.count <= 40, gloss != sentence else { return nil }
        // For the supported verb phrases these fragments omit the verb itself.
        if isPhrase && ["了", "的", "着", "过", "一下"].contains(gloss) { return nil }
        return gloss
    }

    // Chinese adds a classifier to counted nouns (e.g. 70 起森林火灾).
    // The model may align both the classifier and the head to the English noun.
    // Accept the enclosing, independently marked compound only when all its
    // remaining words are nouns and the classifier follows an explicit number.
    // Never join unrelated highlighted spans or guess from a dictionary sense.
    private static func countedNounMeaning(in output: AttributedString, passage: Passage, requiredLink: URL?) -> String? {
        guard ContextWordAlignment.nounHeadRange(passage) != nil else { return nil }
        let strong = output.runs.filter { $0.inlinePresentationIntent?.contains(.stronglyEmphasized) == true }
        let compound = output.runs.filter { $0.inlinePresentationIntent?.contains(.emphasized) == true }
        guard strong.count == 2, let first = strong.first, let last = strong.last,
              compound.first?.range.lowerBound == first.range.lowerBound,
              compound.last?.range.upperBound == last.range.upperBound,
              zip(compound, compound.dropFirst()).allSatisfy({ $0.range.upperBound == $1.range.lowerBound }) else { return nil }
        if let requiredLink, !compound.allSatisfy({ $0.link == requiredLink }) { return nil }
        let classifier = String(output[first.range].characters)
        guard classifier.count == 1, "个位名条张件只头匹座辆艘架起场次份本部家所间".contains(classifier),
              String(output[..<first.range.lowerBound].characters).range(of: #"[0-9０-９零〇一二两三四五六七八九十百千万亿]+[多余]?\s*$"#, options: .regularExpression) != nil else { return nil }
        let gloss = String(output[first.range.upperBound..<last.range.upperBound].characters)
        guard !gloss.isEmpty, gloss.count <= 12 else { return nil }
        let tagger = NLTagger(tagSchemes: [.lexicalClass])
        tagger.string = gloss
        tagger.setLanguage(.simplifiedChinese, range: gloss.startIndex..<gloss.endIndex)
        var nounsOnly = true
        tagger.enumerateTags(in: gloss.startIndex..<gloss.endIndex, unit: .word, scheme: .lexicalClass) { tag, _ in
            if tag != .noun { nounsOnly = false }
            return nounsOnly
        }
        return nounsOnly ? gloss : nil
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

    static func translate(_ passage: Passage, session: TranslationSession, dictionary: @autoclosure () async -> [String], trace: LookupTrace = LookupTrace(),
                          onSentence: ((String) -> Void)? = nil, onExcerpt: ((LookupResult) async -> Void)? = nil) async throws -> LookupResult {
        let marked: ((AttributedString) async throws -> Response)?
        if #available(macOS 26.4, *) {
            marked = { value in
                let began = LookupTrace.now
                defer { trace.record("model.marked", since: began) }
                let response = try await session.translate(value)
                return Response(text: response.targetText, attributed: response.attributedTargetText)
            }
        } else { marked = nil }
        let plain: (String) async throws -> String = { value in
            let began = LookupTrace.now
            defer { trace.record("model.plain", since: began) }
            return try await session.translate(value).targetText
        }
        let batch: ([String]) async throws -> [String] = { values in
            let began = LookupTrace.now
            defer { trace.record("model.batch", since: began) }
            let requests = values.enumerated().map { TranslationSession.Request(sourceText: $0.element, clientIdentifier: String($0.offset)) }
            let responses = try await session.translations(from: requests)
            return try values.indices.map { index in
                let matches = responses.filter { $0.clientIdentifier == String(index) }
                guard matches.count == 1, matches[0].sourceText == values[index] else { throw CocoaError(.coderInvalidValue) }
                return matches[0].targetText
            }
        }
        return try await translate(passage, provider: Provider(plain: plain, marked: marked, batch: batch, supportsContextLinks: marked != nil), dictionary: await dictionary(), trace: trace, onSentence: onSentence, onExcerpt: onExcerpt)
    }

    static let excerptLink = URL(string: "waxlookup://context")!

    static func linkedContext(_ passage: Passage, excerpt: SentenceExcerpt) -> AttributedString? {
        guard excerpt.isTruncated, let selection = passage.selection, let shortened = excerpt.passage.selection,
              var value = markedSentence(passage) else { return nil }
        let range = NSRange(location: selection.location - shortened.location, length: excerpt.passage.context.utf16.count)
        guard let source = Range(range, in: passage.context), passage.context[source] == excerpt.passage.context,
              let selected = Range(range, in: value) else { return nil }
        value[selected].link = excerptLink
        return value
    }

    static func linkedExcerpt(_ value: AttributedString) -> String? {
        var span: Range<AttributedString.Index>?
        for run in value.runs where run.link == excerptLink {
            if let previous = span, previous.upperBound != run.range.lowerBound { return nil }
            span = (span?.lowerBound ?? run.range.lowerBound)..<run.range.upperBound
        }
        guard let span else { return nil }
        let text = String(value[span].characters).trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, text != String(value.characters).trimmingCharacters(in: .whitespacesAndNewlines) else { return nil }
        return text
    }

    private static func translateContext(_ passage: Passage, term: ReadingPhrase?, provider: Provider) async throws -> String {
        if #available(macOS 26.4, *), let term, passage.sourceLanguage == "en", let translate = provider.marked,
           let selection = passage.selection, let hit = Range(selection, in: passage.context), passage.context[hit] == passage.text {
            var protected = AttributedString(term.translation)
            protected.translation.skipsTranslation = true
            let input = AttributedString(passage.context[..<hit.lowerBound]) + protected + AttributedString(passage.context[hit.upperBound...])
            if let response = try? await translate(input), response.text.contains(term.translation) {
                try Task.checkCancellation()
                // Apple may surround a protected run with spaces even between Chinese characters.
                let spelling = NSRegularExpression.escapedPattern(for: term.translation)
                return response.text
                    .replacingOccurrences(of: #"(?<=[\p{Han}，、：（《]) +(?="# + spelling + ")", with: "", options: .regularExpression)
                    .replacingOccurrences(of: "(?<=" + spelling + #") +(?=[\p{Han}，。！？；：、）》])"#, with: "", options: .regularExpression)
            }
            try Task.checkCancellation()
        }
        return try await provider.plain(passage.context)
    }

    static func translate(_ passage: Passage, provider: Provider, dictionary: @autoclosure () async -> [String], trace: LookupTrace = LookupTrace(),
                          onSentence: ((String) -> Void)? = nil, onExcerpt: ((LookupResult) async -> Void)? = nil) async throws -> LookupResult {
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
        let term = LocalTerminology.lookup(passage)
        var fullTranslation: String?
        // One translation can retain the exact word, its compound and the shown
        // excerpt as independent spans, while still translating the whole source.
        // Providers that cannot preserve links keep the established recovery path.
        if term == nil, !passage.isPhrase, passage.sourceLanguage == "en", passage.context.utf16.count <= 4000,
           provider.supportsContextLinks, let translate = provider.marked, let input = linkedContext(passage, excerpt: excerpt) {
            let began = LookupTrace.now
            if let response = try? await translate(input) {
                // Even when formatting is dropped, this is still the complete
                // original sentence. Do not translate it a second time later.
                fullTranslation = response.text
                if let attributed = response.attributed, let short = linkedExcerpt(attributed),
                   let aligned = alignedMeaning(in: attributed, passage: passage, requiredLink: excerptLink) {
                    try Task.checkCancellation()
                    let gloss = needsBoundaryVerification(aligned) ? verifiedBoundaryMeaning(aligned, references: await dictionary()) : aligned
                    if let gloss {
                        var value = makeResult(for: passage, meaning: gloss, origin: .sentence, sentence: response.text)
                        value.excerptTranslation = TranslationOutput.normalize(short)
                        if value.isUsable { trace.record("translation.linked_context", since: began); return value }
                    }
                }
            }
            try Task.checkCancellation()
            trace.record("translation.linked_context_fallback", since: began)
        }
        if let term, !passage.context.isEmpty, passage.context != passage.text {
            let began = LookupTrace.now
            let sentence = try await translateContext(excerpt.passage, term: term.phrase, provider: provider)
            trace.record("translation.term_sentence", since: began)
            output = LookupResult(meaning: TranslationOutput.normalize(term.meaning), origin: .term,
                                  sentenceTranslation: TranslationOutput.normalize(sentence, target: passage.sourceLanguage.hasPrefix("zh") ? "en" : "zh-Hans"))
        } else {
            output = try await translateMeaning(excerpt.passage, retry: SentenceExcerpt.alignmentRetry(passage), provider: provider, dictionary: dictionary, trace: trace, onSentence: onSentence)
        }
        try Task.checkCancellation()
        if excerpt.isTruncated {
            output.excerptTranslation = output.sentenceTranslation
            output.sentenceTranslation = nil
            if output.isUsable, output.origin == .sentence || output.origin == .term {
                await onExcerpt?(output)
                try Task.checkCancellation()
            }
            let began = LookupTrace.now
            do {
                let translated: String
                if let fullTranslation { translated = fullTranslation }
                else { translated = try await translateContext(passage, term: term?.phrase, provider: provider) }
                output.sentenceTranslation = TranslationOutput.normalize(translated, target: passage.sourceLanguage.hasPrefix("zh") ? "en" : "zh-Hans")
            } catch { try Task.checkCancellation() } // An optional full sentence must not erase the usable excerpt.
            try Task.checkCancellation()
            trace.record("translation.full_context", since: began)
        }
        // Recovery uses the whole original passage, retaining conditions and
        // the exact occurrence even when the card shows a shorter excerpt.
        if output.origin == .unresolved, !passage.isPhrase || SentenceContext.isPhrasalVerb(passage.text),
           let sentence = output.sentenceTranslation,
           let alignment = ContextWordAlignment(passage, translation: sentence, focus: .nounHead) {
            let began = LookupTrace.now
            if let recovered = try await alignment.recover(batch: provider.batch, using: provider.plain) {
                let gloss = needsBoundaryVerification(recovered) && !passage.isPhrase
                    ? verifiedBoundaryMeaning(recovered, references: await dictionary() + [output.wordReference].compactMap { $0 }) : recovered
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

    private static func translateMeaning(_ passage: Passage, retry: Passage?, provider: Provider, dictionary: () async -> [String], trace: LookupTrace,
                                         onSentence: ((String) -> Void)?) async throws -> LookupResult {
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

        if passage.isPhrase, passage.sourceLanguage == "en", !SentenceContext.isPhrasalVerb(passage.text) {
            try Task.checkCancellation()
            if !sentence.isEmpty { onSentence?(TranslationOutput.normalize(sentence)) }
            let independent: String
            do { independent = try await provider.plain(passage.text) }
            catch is CancellationError { throw CancellationError() }
            catch { independent = "" }
            try Task.checkCancellation()
            let reference = result(independent, .standalone, sentence)
            guard let alignedGloss else { return reference }
            let candidate = TranslationOutput.normalize(alignedGloss)
            let boundaries = CharacterSet.whitespacesAndNewlines.union(.punctuationCharacters)
            if reference.isUsable, candidate == reference.meaning.trimmingCharacters(in: boundaries) {
                return result(candidate, .sentence, sentence)
            }
            // A clipped function word can already explain the disagreement.
            if reference.isUsable, verifiedBoundaryMeaning(candidate, references: [reference.meaning]) != nil { return reference }
            // Two literal markings must reproduce the same target span at this occurrence.
            // Only complete boundary tokens may separate that span from the first alignment.
            guard candidate.count >= 2,
                  let alignment = ContextWordAlignment(passage, translation: sentence),
                  let confirmed = try await alignment.recover(exactPhrase: true, batch: provider.batch, using: provider.plain),
                  confirmed.count >= 2, !needsBoundaryVerification(confirmed),
                  verifiedBoundaryMeaning(candidate, references: [confirmed]) != nil else { return reference }
            return result(confirmed, .sentence, sentence)
        }

        if let gloss = alignedGloss {
            if passage.sourceLanguage.hasPrefix("zh") || passage.isPhrase || !needsBoundaryVerification(gloss) { return result(gloss, .sentence, sentence) }
            if let verified = verifiedBoundaryMeaning(gloss, references: await dictionary()) { return result(verified, .sentence, sentence) }
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
                if let verified = verifiedBoundaryMeaning(gloss, references: await dictionary()) { return result(verified, .sentence, sentence) }
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
            guard let reference = await dictionary().first else { throw error }
            return referenceResult(reference, origin: .dictionary)
        }
    }
}
