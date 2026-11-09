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

    init(_ original: Passage) {
        let text = original.context
        let limit = original.sourceLanguage.hasPrefix("zh") ? 60 : 160
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

    private static func slice(_ original: Passage, bounds: Range<String.Index>) -> Passage {
        let context = String(original.context[bounds])
        let offset = bounds.lowerBound.utf16Offset(in: original.context)
        let shifted: (NSRange?) -> NSRange? = { range in
            range.map { NSRange(location: $0.location - offset, length: $0.length) }
        }
        return Passage(text: original.text, context: context, selection: shifted(original.selection),
                       anchor: shifted(original.anchor), language: original.sourceLanguage)
    }

}

enum SentenceContext {
    static func passage(in lines: [TextLine], language: String? = nil) throws -> Passage {
        guard let anchor = lines.firstIndex(where: { $0.hit != nil }),
              let wordRange = lines[anchor].hit,
              let range = Range(wordRange, in: lines[anchor].text) else { throw ReaderError.noText }
        let word = String(lines[anchor].text[range])
        let heading = lines[anchor].text.trimmingCharacters(in: .whitespacesAndNewlines)
        let otherHeights = lines.enumerated().filter { $0.offset != anchor }.map { $0.element.frame.height }
        let prominent = otherHeights.min().map { lines[anchor].frame.height >= $0 * 1.35 } ?? false
        // A short, prominent all-katakana heading separated by middle dots is
        // a title unit. Never apply this to ordinary Japanese prose or metadata.
        if prominent, heading.count <= 48, heading.contains("・"),
           heading.range(of: #"^[\p{Katakana}ー・ 　]+$"#, options: .regularExpression) != nil {
            return Passage(text: heading, context: heading, language: language ?? "ja")
        }
        let above = neighbors(from: anchor, in: lines, upward: true)
        let below = neighbors(from: anchor, in: lines, upward: false)
        var paragraph = ""
        var wordOffset = 0
        for index in Array(above.reversed()) + [anchor] + below {
            let text = lines[index].text
            if paragraph.last == "\u{00ad}" { paragraph.removeLast() }
            else if needsSpace(after: paragraph.last, before: text.first) { paragraph += " " }
            if index == anchor { wordOffset = paragraph.utf16.count + wordRange.location }
            paragraph += text
        }
        let selected = String.Index(utf16Offset: wordOffset, in: paragraph)
        let sentences = NLTokenizer(unit: .sentence)
        sentences.string = paragraph
        let bounds = sentences.tokenRange(at: selected)
        let slice = paragraph[bounds].drop(while: { $0.isWhitespace })
        let context = String(slice).trimmingCharacters(in: .whitespacesAndNewlines)
        let offset = wordOffset - slice.startIndex.utf16Offset(in: paragraph)
        let hit = NSRange(location: offset, length: wordRange.length)
        let token = Passage(text: word, context: context, selection: hit, language: language,
                            nearbyContext: paragraph, nearbySelection: NSRange(location: wordOffset, length: wordRange.length))
        let sentenceRange = NSRange(context.startIndex..., in: context)
        guard let match = englishPhrases.matches(in: context, range: sentenceRange).first(where: {
            NSIntersectionRange($0.range, hit) == hit
        }), (token.sourceLanguage == "en" || token.sourceLanguage.hasPrefix("zh")), let range = Range(match.range, in: context) else { return token }
        return Passage(text: String(context[range]), context: context, selection: match.range, anchor: hit, language: language)
    }

    // Match only contiguous expressions, including ordinary inflections. Keep the
    // actual spelling for display and exclude fragments of hyphenated compounds.
    private static let englishPhrases = try! NSRegularExpression(
        pattern: #"""
            (?<![\w‐‑-])
            (?:
                (?:rule|rules|ruled|ruling)    \h+ out
              | (?:run|runs|ran|running)       \h+ out \h+ of
              | (?:look|looks|looked|looking)  \h+ up
              | attention \h+ mask
              | padding \h+ token
            )
            (?![\w‐‑-])
            """#,
        options: [.caseInsensitive, .allowCommentsAndWhitespace])

    private static func neighbors(from anchor: Int, in lines: [TextLine], upward: Bool) -> [Int] {
        var result: [Int] = []
        var current = lines[anchor].frame
        while true {
            // A soft wrap stays in the same column at roughly the same font size
            // and baseline spacing. Pixel distances scale with the recognized type.
            let candidates = lines.indices.filter { i in
                let next = lines[i].frame
                let listStart = #"^\s*(?:[•●▪◦*+-]|[0-9]+[.)、])\s*"#
                if upward {
                    let currentLine = result.last.map { lines[$0].text } ?? lines[anchor].text
                    if currentLine.range(of: listStart, options: .regularExpression) != nil { return false }
                } else if lines[i].text.range(of: listStart, options: .regularExpression) != nil { return false }
                // Prominent headings and smaller metadata are distinct blocks.
                if max(current.height, next.height) > min(current.height, next.height) * 1.3 { return false }
                let height = max(current.height, next.height)
                let step = upward ? next.midY - current.midY : current.midY - next.midY
                let overlap = min(current.maxX, next.maxX) - max(current.minX, next.minX)
                let aligned = abs(current.minX - next.minX) <= 2.5 * height ||
                              abs(current.midX - next.midX) <= 1.5 * height
                return step >= 0.6 * height && step <= 2.05 * height &&
                       min(current.height, next.height) >= 0.63 * height &&
                       overlap >= 0.4 * min(current.width, next.width) && aligned
            }
            guard let next = candidates.min(by: { lhs, rhs in
                let a = lines[lhs].frame, b = lines[rhs].frame
                return abs(a.midY - current.midY) + 0.15 * abs(a.minX - current.minX) <
                       abs(b.midY - current.midY) + 0.15 * abs(b.minX - current.minX)
            }) else { break }
            result.append(next)
            current = lines[next].frame
        }
        return result
    }

    private static func needsSpace(after last: Character?, before first: Character?) -> Bool {
        guard let last, let first, last != "-", last != "‐" else { return false }
        let joinedScripts = #"^[\p{Han}\p{Hiragana}\p{Katakana}。、，；：！？「」『』]$"#
        return !(String(last).range(of: joinedScripts, options: .regularExpression) != nil &&
                 String(first).range(of: joinedScripts, options: .regularExpression) != nil)
    }
}
