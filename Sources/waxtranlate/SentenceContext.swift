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
                       anchor: shifted(original.anchor), language: original.sourceLanguage, structure: original.structure)
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
            return Passage(text: heading, context: heading, language: language ?? "ja", structure: .title)
        }
        let singleStructure = structure(of: heading)
        if singleStructure == .title || singleStructure == .path {
            let leading = lines[anchor].text.prefix(while: { $0.isWhitespace }).utf16.count
            return Passage(text: word, context: heading, selection: NSRange(location: wordRange.location - leading, length: wordRange.length), language: language, structure: singleStructure)
        }
        let above = neighbors(from: anchor, in: lines, upward: true)
        let below = neighbors(from: anchor, in: lines, upward: false)
        var paragraph = ""
        var wordOffset = 0
        for index in Array(above.reversed()) + [anchor] + below {
            let raw = lines[index].text
            let prefix = commentPrefix(raw)
            let strip = prefix > 0 && (index != anchor || wordRange.location >= prefix) ? prefix : 0
            let text = String(raw.dropFirst(strip))
            if paragraph.last == "\u{00ad}" { paragraph.removeLast() }
            else if needsSpace(after: paragraph.last, before: text.first) { paragraph += " " }
            if index == anchor { wordOffset = paragraph.utf16.count + wordRange.location - raw.prefix(strip).utf16.count }
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
        let isList = heading.range(of: #"^\s*(?:[•●▪◦*+-]|[0-9]+[.)、])\s*"#, options: .regularExpression) != nil
        let isPath = heading.range(of: #"^(?:[A-Za-z]:)?[\w./\\-]+[/\\][\w.\-]+$"#, options: .regularExpression) != nil
        let incomplete = context.hasPrefix("…") || context.hasSuffix("…") || context.hasPrefix("...") || context.hasSuffix("...")
        let possibleTitle = prominent && heading.count <= 100 && heading.range(of: "[。！？.!?]", options: .regularExpression) == nil
        let structure: Passage.Structure = isPath ? .path : isList ? .list : incomplete ? .fragment : possibleTitle ? .title : .sentence
        let token = Passage(text: word, context: context, selection: hit, language: language,
                            nearbyContext: paragraph, nearbySelection: NSRange(location: wordOffset, length: wordRange.length), structure: structure)
        let sentenceRange = NSRange(context.startIndex..., in: context)
        guard let match = englishPhrases.matches(in: context, range: sentenceRange).first(where: {
            NSIntersectionRange($0.range, hit) == hit
        }), (token.sourceLanguage == "en" || token.sourceLanguage.hasPrefix("zh")), let range = Range(match.range, in: context) else { return token }
        return Passage(text: String(context[range]), context: context, selection: match.range, anchor: hit, language: language, structure: structure)
    }

    // Keep the original capture separate from the semantic block. Hard wraps
    // inside prose/comments may continue; headings, lists, blank lines and code
    // transitions stop the block before sentence tokenization runs.
    static func passage(in text: String, selection: NSRange, language: String? = nil) throws -> Passage {
        let block = try evidence(in: text, selection: selection)
        var lines: [TextLine] = []
        var offset = 0
        let pieces = block.text.components(separatedBy: "\n")
        for (index, line) in pieces.enumerated() {
            let span = NSRange(location: offset, length: line.utf16.count)
            let hit = NSIntersectionRange(span, block.selection).length > 0 ?
                NSRange(location: block.selection.location - offset, length: block.selection.length) : nil
            lines.append(TextLine(text: line, frame: CGRect(x: 0, y: (pieces.count - index) * 25, width: 800, height: 18), hit: hit))
            offset += line.utf16.count + 1
        }
        return try passage(in: lines, language: language)
    }

    static func evidence(in text: String, selection: NSRange) throws -> (text: String, selection: NSRange) {
        guard Range(selection, in: text) != nil else { throw ReaderError.noText }
        let pieces = text.components(separatedBy: "\n")
        var ranges: [NSRange] = []
        var offset = 0
        for line in pieces {
            ranges.append(NSRange(location: offset, length: line.utf16.count))
            offset += line.utf16.count + 1
        }
        guard let anchor = ranges.firstIndex(where: { NSLocationInRange(selection.location, $0) }) else { throw ReaderError.noText }
        let kind = blockKind(pieces[anchor])
        var left = anchor, right = anchor
        if kind == "prose" || kind == "comment" {
            while left > 0 && blockKind(pieces[left - 1]) == kind { left -= 1 }
            while right + 1 < pieces.count && blockKind(pieces[right + 1]) == kind { right += 1 }
        }
        let start = ranges[left].location
        let stop = NSMaxRange(ranges[right])
        let bounds = NSRange(location: start, length: stop - start)
        guard NSMaxRange(selection) <= stop, let slice = Range(bounds, in: text) else { throw ReaderError.noText }
        return (String(text[slice]), NSRange(location: selection.location - start, length: selection.length))
    }

    private static func structure(of text: String) -> Passage.Structure {
        switch blockKind(text) {
        case "title": return .title
        case "path": return .path
        case "list": return .list
        case "fragment": return .fragment
        default: return .sentence
        }
    }

    private static func blockKind(_ text: String) -> String {
        let line = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if line.isEmpty { return "empty" }
        if commentPrefix(text) > 0 { return "comment" }
        if line.range(of: #"^(?:[A-Za-z]:)?[\w./\\-]+[/\\][\w.\-]+$"#, options: .regularExpression) != nil { return "path" }
        if line.range(of: #"^(?:[•●▪◦*+-]|[0-9]+[.)、])\s*"#, options: .regularExpression) != nil { return "list" }
        if line.range(of: #"^#{1,6}\s+"#, options: .regularExpression) != nil { return "title" }
        if codeLine(line) { return "code" }
        if line.hasPrefix("…") || line.hasSuffix("…") || line.hasPrefix("...") || line.hasSuffix("...") { return "fragment" }
        return "prose"
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
                let currentIndex = result.last ?? anchor
                let currentText = lines[currentIndex].text
                let candidateText = lines[i].text
                let currentComment = commentPrefix(currentText) > 0
                let candidateComment = commentPrefix(candidateText) > 0
                // A comment is a prose block, never the following declaration or
                // field column. Each adjacent marked comment line may soft-wrap.
                if currentComment != candidateComment { return false }
                if blockKind(currentText) == "title" || blockKind(candidateText) == "title" { return false }
                if codeLine(currentText) != codeLine(candidateText) { return false }
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

    // Strip only a line-leading comment marker followed by whitespace.
    // URLs, division, paths, and slashes inside the sentence remain untouched.
    private static func commentPrefix(_ text: String) -> Int {
        guard let range = text.range(of: #"^\s*//[/!]?(?:\s+|$)"#, options: .regularExpression) else { return 0 }
        return text[range].count
    }

    private static func codeLine(_ text: String) -> Bool {
        if commentPrefix(text) > 0 { return false }
        return text.range(of: #"^\s*(?:(?:type|func|struct|class|enum|import|package|return|let|var|const)\s|[{}]\s*$|[A-Za-z_]\w*\s+(?:string|int|bool|float\d*|[A-Za-z_]\w*\.)\b)"#, options: .regularExpression) != nil
    }

    private static func needsSpace(after last: Character?, before first: Character?) -> Bool {
        guard let last, let first, last != "-", last != "‐" else { return false }
        let joinedScripts = #"^[\p{Han}\p{Hiragana}\p{Katakana}。、，；：！？「」『』]$"#
        return !(String(last).range(of: joinedScripts, options: .regularExpression) != nil &&
                 String(first).range(of: joinedScripts, options: .regularExpression) != nil)
    }
}
