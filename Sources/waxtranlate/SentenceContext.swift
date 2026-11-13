import Foundation
import NaturalLanguage

struct TextLine {
    let text: String
    let frame: CGRect     // image pixels, bottom-left origin
    let hit: NSRange?     // UTF-16 range of the token under the pointer
}

// Translate the same bounded excerpt that the compact card displays. Keep the
// original Passage for full context, saving and exact-occurrence cache keys.
struct SentenceExcerpt {
    let passage: Passage
    let isTruncated: Bool

    init(_ original: Passage, limit requestedLimit: Int? = nil) {
        let text = original.context
        let limit = requestedLimit ?? (original.sourceLanguage.hasPrefix("zh") ? 60 : 160)
        guard text.count > limit, let selection = original.selection,
              let hit = Range(selection, in: text), text[hit] == original.text else {
            passage = original; isTruncated = false; return
        }
        let separators = CharacterSet(charactersIn: ",;:，；：—")
        let isSeparator: (Character) -> Bool = { $0.unicodeScalars.allSatisfy { separators.contains($0) } }
        let clauseStart = text[..<hit.lowerBound].lastIndex(where: isSeparator).map { text.index(after: $0) } ?? text.startIndex
        let clauseEnd = text[hit.upperBound...].firstIndex(where: isSeparator) ?? text.endIndex
        let clause = text[clauseStart..<clauseEnd].trimmingCharacters(in: .whitespacesAndNewlines)
        if clause.count >= max(24, original.text.count + 12), clause.count <= limit,
           let bounds = text.range(of: clause, range: clauseStart..<clauseEnd) {
            passage = Self.slice(original, bounds: bounds); isTruncated = true; return
        }
        let tokenizer = NLTokenizer(unit: .word)
        tokenizer.string = text
        let words = tokenizer.tokens(for: text.startIndex..<text.endIndex)
        guard let first = words.firstIndex(where: { $0.upperBound > hit.lowerBound }),
              let last = words.lastIndex(where: { $0.lowerBound < hit.upperBound }) else {
            passage = original; isTruncated = false; return
        }
        var left = first, right = last
        while true {
            let canLeft = left > 0 && text[words[left - 1].lowerBound..<words[right].upperBound].count <= limit
            let canRight = right + 1 < words.count && text[words[left].lowerBound..<words[right + 1].upperBound].count <= limit
            guard canLeft || canRight else { break }
            if canLeft && (!canRight || text[words[left].lowerBound..<hit.lowerBound].count <= text[hit.upperBound..<words[right].upperBound].count) {
                left -= 1
            } else { right += 1 }
        }
        let start = left == 0 ? text.startIndex : words[left].lowerBound
        let end = right + 1 == words.count ? text.endIndex : words[right].upperBound
        passage = Self.slice(original, bounds: start..<end)
        isTruncated = passage.context != text
    }

    static func alignmentRetry(_ original: Passage) -> Passage? {
        guard original.hasCompleteContext, original.sourceLanguage == "en" else { return nil }
        let shorter = SentenceExcerpt(original, limit: 64)
        guard shorter.isTruncated, let hit = original.selection, let shifted = shorter.passage.selection else { return nil }
        let start = hit.location - shifted.location
        let source = original.context as NSString
        let end = start + shorter.passage.context.utf16.count
        guard start >= 0, end <= source.length else { return nil }
        let omitted = source.substring(to: start) + " " + source.substring(from: end)
        // Do not remove a negation, condition or correction to get an alignment.
        guard omitted.range(of: #"\b(?:no|not|never|cannot|neither|nor|without|if|unless|until|whether|only|except|rather|instead)\b|n['’]t\b"#,
                            options: [.regularExpression, .caseInsensitive]) == nil else { return nil }
        for (open, close) in [("(", ")"), ("[", "]"), ("{", "}")] {
            guard shorter.passage.context.filter({ String($0) == open }).count == shorter.passage.context.filter({ String($0) == close }).count else { return nil }
        }
        return shorter.passage
    }

    private static func slice(_ original: Passage, bounds: Range<String.Index>) -> Passage {
        let context = String(original.context[bounds])
        let offset = bounds.lowerBound.utf16Offset(in: original.context)
        let shifted: (NSRange?) -> NSRange? = { range in
            range.map { NSRange(location: $0.location - offset, length: $0.length) }
        }
        return Passage(text: original.text, context: context, selection: shifted(original.selection),
                       anchor: shifted(original.anchor), language: original.sourceLanguage, structure: original.structure, extent: original.extent)
    }

}

enum SentenceContext {
    static func passage(in lines: [TextLine], language: String? = nil, captureBounds: CGRect? = nil) throws -> Passage {
        try build(lines, language: language, source: .ocr, captureBounds: captureBounds)
    }

    static func passage(in text: String, selection: NSRange, language: String? = nil) throws -> Passage {
        try build(ContextBoundary.editorLines(text, selection: selection), language: language, source: .editor, captureBounds: nil)
    }

    static func evidence(in text: String, selection: NSRange) throws -> (text: String, selection: NSRange) {
        try ContextBoundary.evidence(text, selection: selection)
    }

    private static func build(_ raw: [TextLine], language: String?, source: ContextBoundary.Source, captureBounds: CGRect?) throws -> Passage {
        let lines = source == .ocr ? ContextBoundary.coalesce(raw, language: language) : raw
        guard let anchor = lines.firstIndex(where: { $0.hit != nil }), let rawHit = lines[anchor].hit else { throw ReaderError.noText }
        let heading = lines[anchor].text.trimmingCharacters(in: .whitespacesAndNewlines)
        let heights = lines.enumerated().filter { $0.offset != anchor }.map { $0.element.frame.height }.sorted()
        let bodyHeight = heights.isEmpty ? nil : heights[heights.count / 2]
        let analysis = try ContextBoundary.analyze(lines, source: source, captureBounds: captureBounds, language: language)
        let prominent = source == .ocr && ![Passage.Structure.code, .path, .list, .title].contains(analysis.structure) &&
            bodyHeight.map { lines[anchor].frame.height >= $0 * 1.6 } == true
        if prominent, heading.count <= 48, heading.contains("・"),
           heading.range(of: #"^[\p{Katakana}ー・ 　]+$"#, options: .regularExpression) != nil {
            return Passage(text: heading, context: heading, language: language ?? "ja", structure: .title)
        }
        if prominent, heading.count <= 100, heading.range(of: "[。！？.!?]", options: .regularExpression) == nil {
            let leading = lines[anchor].text.prefix(while: { $0.isWhitespace }).utf16.count
            let hit = NSRange(location: rawHit.location - leading, length: rawHit.length)
            if let selected = Range(hit, in: heading) {
                return Passage(text: String(heading[selected]), context: heading, selection: hit, language: language, structure: .title)
            }
        }
        guard let range = Range(analysis.hit, in: analysis.context) else { throw ReaderError.noText }
        let word = String(analysis.context[range])
        let token = Passage(text: word, context: analysis.context, selection: analysis.hit, anchor: analysis.pointerHit, language: language,
                            nearbyContext: analysis.block, nearbySelection: analysis.blockHit, structure: analysis.structure, extent: analysis.extent)
        let phraseRange = LocalTerminology.phrase(at: token)?.range ?? englishPhrases.matches(in: analysis.context,
            range: NSRange(analysis.context.startIndex..., in: analysis.context)).first {
                NSIntersectionRange($0.range, analysis.hit) == analysis.hit
            }?.range
        guard let phraseRange, phraseRange != token.selection, token.structure != .code, token.structure != .path,
              token.sourceLanguage == "en" || token.sourceLanguage.hasPrefix("zh") else { return token }
        return token.selecting(phraseRange, anchor: analysis.pointerHit) ?? token
    }

    static func isPhrasalVerb(_ text: String) -> Bool {
        let full = NSRange(text.startIndex..., in: text)
        return englishPhrases.firstMatch(in: text, range: full)?.range == full
    }

    private static let englishPhrases = try! NSRegularExpression(
        pattern: #"""
            (?<![\w‐‑-])
            (?:
                (?:rule|rules|ruled|ruling)    \h+ out
              | (?:run|runs|ran|running)       \h+ out \h+ of
              | (?:look|looks|looked|looking)  \h+ up
            )
            (?![\w‐‑-])
            """#,
        options: [.caseInsensitive, .allowCommentsAndWhitespace])
}
