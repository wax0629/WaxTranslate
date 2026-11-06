import Foundation
import NaturalLanguage

struct TextLine {
    let text: String
    let frame: CGRect     // image pixels, bottom-left origin
    let hit: NSRange?     // UTF-16 range of the token under the pointer
}

enum SentenceContext {
    static func passage(in lines: [TextLine]) throws -> Passage {
        guard let anchor = lines.firstIndex(where: { $0.hit != nil }),
              let wordRange = lines[anchor].hit,
              let range = Range(wordRange, in: lines[anchor].text) else { throw ReaderError.noText }
        let word = String(lines[anchor].text[range])
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
        let token = Passage(text: word, context: context, selection: hit)
        let sentenceRange = NSRange(context.startIndex..., in: context)
        guard let match = englishPhrases.matches(in: context, range: sentenceRange).first(where: {
            NSIntersectionRange($0.range, hit) == hit
        }), token.sourceLanguage == "en", let range = Range(match.range, in: context) else { return token }
        return Passage(text: String(context[range]), context: context, selection: match.range, anchor: hit)
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
