import CoreServices
import Foundation
import NaturalLanguage
import Translation

struct LookupResult {
    enum Origin { case sentence, dictionary, word, region }
    let meaning: String
    let origin: Origin
    var sentenceTranslation: String? = nil
}

enum CompactGloss {
    static func candidates(for passage: Passage, language: String) -> [String] {
        guard language == "en", let selection = passage.selection,
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
                    let gloss = String(variant[span])
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
    static func markedSentence(_ passage: Passage) -> AttributedString? {
        guard let selection = passage.selection, let range = Range(selection, in: passage.context),
              passage.context[range] == passage.text else { return nil }
        var mark = AttributedString(passage.context[range])
        mark.inlinePresentationIntent = .stronglyEmphasized
        return AttributedString(passage.context[..<range.lowerBound]) + mark + AttributedString(passage.context[range.upperBound...])
    }

    static func alignedMeaning(in output: AttributedString) -> String? {
        // Accept only one contiguous translated span. Some language pairs may
        // drop the emphasis or apply it to the whole sentence.
        var span: Range<AttributedString.Index>?
        for run in output.runs where run.inlinePresentationIntent?.contains(.stronglyEmphasized) == true {
            if let previous = span, previous.upperBound != run.range.lowerBound { return nil }
            span = (span?.lowerBound ?? run.range.lowerBound)..<run.range.upperBound
        }
        guard let span else { return nil }
        let trim = CharacterSet.whitespacesAndNewlines.union(.punctuationCharacters)
        let gloss = String(output[span].characters).trimmingCharacters(in: trim)
        let sentence = String(output.characters).trimmingCharacters(in: trim)
        guard !gloss.isEmpty, gloss.count <= 40, gloss != sentence else { return nil }
        // Apple can attach the preceding modifier particle to a Chinese adjective
        // (e.g. "的新"). Leave words such as "的确" intact.
        if gloss.first == "的" && gloss.count > 1 {
            let tokenizer = NLTokenizer(unit: .word)
            tokenizer.string = gloss
            tokenizer.setLanguage(.simplifiedChinese)
            let first = tokenizer.tokenRange(at: gloss.startIndex)
            if gloss[first] == "的" { return String(gloss[first.upperBound...]).trimmingCharacters(in: .whitespaces) }
        }
        return gloss
    }

    static func translate(_ passage: Passage, session: TranslationSession, dictionary: [String]) async throws -> LookupResult {
        guard !passage.context.isEmpty, passage.context != passage.text else {
            let text = try await session.translate(passage.text).targetText
            return LookupResult(meaning: text, origin: passage.context.isEmpty ? .region : .word)
        }

        let sentence: String
        if #available(macOS 26.4, *), let marked = markedSentence(passage),
           let response = try? await session.translate(marked) {
            sentence = response.targetText
            if let formatted = response.attributedTargetText, let gloss = alignedMeaning(in: formatted) {
                return LookupResult(meaning: gloss, origin: .sentence, sentenceTranslation: sentence)
            }
        } else {
            try Task.checkCancellation()
            sentence = try await session.translate(passage.context).targetText
        }

        if let match = dictionary.filter({ $0.count > 1 && sentence.contains($0) }).max(by: { $0.count < $1.count }) {
            return LookupResult(meaning: match, origin: .dictionary, sentenceTranslation: sentence)
        }
        do {
            let word = try await session.translate(passage.text).targetText
            return LookupResult(meaning: word, origin: .word, sentenceTranslation: sentence)
        } catch {
            try Task.checkCancellation()
            guard let reference = dictionary.first else { throw error }
            return LookupResult(meaning: reference, origin: .dictionary, sentenceTranslation: sentence)
        }
    }
}
