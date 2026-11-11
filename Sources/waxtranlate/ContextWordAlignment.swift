import Foundation
import NaturalLanguage

// Recover a lost formatting alignment without looking for an arbitrary
// dictionary sense elsewhere in the translation. Each probe marks the exact
// source occurrence (with its adjacent noun modifier when needed). The query
// and stored selection remain unchanged. Two delimited spans must agree on a span
// in the original, unmodified sentence translation.
struct ContextWordAlignment {
    enum Focus { case word, nounHead }
    private enum Marker: CaseIterable {
        case bold, italic, quote
        var pairs: [(String, String)] {
            switch self {
            case .bold: return [("<b>", "</b>")]
            case .italic: return [("<i>", "</i>")]
            case .quote: return [("\"", "\""), ("“", "”"), ("「", "」")]
            }
        }
    }
    private struct Probe { let marker: Marker; let text: String }
    private struct Span { let prefix: String; let text: String; let suffix: String }
    private let probes: [Probe]
    private let target: String
    private let characters: [Character]
    private let wordStarts: Set<Int>
    private let wordEnds: Set<Int>
    private let compoundHead: Bool

    init?(_ passage: Passage, translation: String, focus: Focus = .word) {
        guard passage.sourceLanguage == "en", passage.hasCompleteContext,
              [.sentence, .list].contains(passage.structure),
              !passage.context.isEmpty, passage.context != passage.text,
              !passage.context.contains("<"), !passage.context.contains(">"),
              passage.context.utf16.count <= 4000, passage.text.count <= 80,
              let selection = passage.selection, let selected = Range(selection, in: passage.context),
              passage.context[selected] == passage.text else { return nil }
        let target = TranslationOutput.normalize(translation)
        self.target = target
        let characters = Array(target)
        self.characters = characters
        guard !characters.isEmpty, characters.count <= 2048 else { return nil }
        let available = Marker.allCases.filter { marker in
            !marker.pairs.contains { pair in
                passage.context.contains(pair.0) || passage.context.contains(pair.1) || target.contains(pair.0) || target.contains(pair.1)
            }
        }
        guard available.count >= 2 else { return nil }
        let focused = focus == .nounHead ? Self.nounHeadRange(passage).flatMap { Range($0, in: passage.context) } ?? selected : selected
        probes = available.map { marker in
            let (open, close) = marker.pairs[0]
            return Probe(marker: marker, text: String(passage.context[..<focused.lowerBound]) + open + String(passage.context[focused]) + close + String(passage.context[focused.upperBound...]))
        }
        let tokenizer = NLTokenizer(unit: .word)
        tokenizer.string = target
        tokenizer.setLanguage(.simplifiedChinese)
        var offsets = Dictionary(uniqueKeysWithValues: target.indices.enumerated().map { ($0.element, $0.offset) })
        offsets[target.endIndex] = characters.count
        let words = tokenizer.tokens(for: target.startIndex..<target.endIndex)
        wordStarts = Set(words.compactMap { offsets[$0.lowerBound] })
        wordEnds = Set(words.compactMap { offsets[$0.upperBound] })
        compoundHead = Self.isCompoundNounHead(passage)
    }

    func recover(using translate: (String) async throws -> String) async throws -> String? {
        var agreement: Range<Int>?
        var confirmations = 0
        for (index, probe) in probes.enumerated() {
            try Task.checkCancellation()
            let translated: String
            do { translated = try await translate(probe.text) }
            catch is CancellationError { throw CancellationError() }
            catch { try Task.checkCancellation(); return nil }
            try Task.checkCancellation()
            if let span = parse(translated, marker: probe.marker), let projected = project(span) {
                if let previous = agreement {
                    let lower = max(previous.lowerBound, projected.lowerBound)
                    let upper = min(previous.upperBound, projected.upperBound)
                    // Conflicting locations are not resolved by cherry-picking
                    // another probe, even when the sentence contains both senses.
                    guard lower < upper else { return nil }
                    agreement = lower..<upper
                } else { agreement = projected }
                confirmations += 1
                if confirmations == 2, let agreement {
                    let start = target.index(target.startIndex, offsetBy: agreement.lowerBound)
                    let end = target.index(target.startIndex, offsetBy: agreement.upperBound)
                    let range = Self.completeTargetWord(NSRange(start..<end, in: target), in: target, compoundHead: compoundHead)
                    guard let span = Range(range, in: target) else { return nil }
                    return String(target[span]).trimmingCharacters(in: .whitespacesAndNewlines.union(.punctuationCharacters))
                }
            }
            if confirmations + probes.count - index - 1 < 2 { return nil }
        }
        return nil
    }

    // A compound's head can map to only the last character of a Chinese word
    // (for example, a head noun inside a two-noun English compound). Preserve
    // the complete target word. A preceding modifier must keep its own span.
    static func isCompoundNounHead(_ passage: Passage) -> Bool {
        nounHeadRange(passage) != nil
    }

    private static func nounHeadRange(_ passage: Passage) -> NSRange? {
        guard passage.sourceLanguage == "en", !passage.isPhrase, let selection = passage.selection,
              let selected = Range(selection, in: passage.context), passage.context[selected] == passage.text else { return nil }
        let tokenizer = NLTokenizer(unit: .word)
        tokenizer.string = passage.context
        tokenizer.setLanguage(.english)
        let words = tokenizer.tokens(for: passage.context.startIndex..<passage.context.endIndex)
        guard let index = words.firstIndex(of: selected), index > 0 else { return nil }
        let previous = words[index - 1]
        let gap = passage.context[previous.upperBound..<selected.lowerBound]
        guard !gap.isEmpty, gap.allSatisfy({ $0 == " " || $0 == "\t" }) else { return nil }
        let tagger = NLTagger(tagSchemes: [.lexicalClass])
        tagger.string = passage.context
        tagger.setLanguage(.english, range: passage.context.startIndex..<passage.context.endIndex)
        guard tagger.tag(at: previous.lowerBound, unit: .word, scheme: .lexicalClass).0 == .noun,
              tagger.tag(at: selected.lowerBound, unit: .word, scheme: .lexicalClass).0 == .noun else { return nil }
        return NSRange(previous.lowerBound..<selected.upperBound, in: passage.context)
    }

    static func completeTargetWord(_ range: NSRange, in text: String, compoundHead: Bool) -> NSRange {
        guard compoundHead, let selected = Range(range, in: text) else { return range }
        let tokenizer = NLTokenizer(unit: .word)
        tokenizer.string = text
        tokenizer.setLanguage(.simplifiedChinese)
        let words = tokenizer.tokens(for: text.startIndex..<text.endIndex)
        if let index = words.firstIndex(where: { $0.lowerBound <= selected.lowerBound && $0.upperBound >= selected.upperBound }),
           text[words[index]].count <= 12 {
            let word = words[index]
            // The Chinese tokenizer can split a compound into a noun and a
            // one-character head. Complete that adjacent noun combination,
            // without swallowing a preceding verb or crossing punctuation.
            if text[word].count == 1, index > 0, words[index - 1].upperBound == word.lowerBound {
                let previous = words[index - 1]
                let tagger = NLTagger(tagSchemes: [.lexicalClass])
                tagger.string = text
                tagger.setLanguage(.simplifiedChinese, range: text.startIndex..<text.endIndex)
                if tagger.tag(at: previous.lowerBound, unit: .word, scheme: .lexicalClass).0 == .noun,
                   text[previous.lowerBound..<word.upperBound].count <= 12 {
                    return NSRange(previous.lowerBound..<word.upperBound, in: text)
                }
            }
            return NSRange(word, in: text)
        }
        return range
    }

    private func parse(_ output: String, marker: Marker) -> Span? {
        let text = TranslationOutput.normalize(output)
        for (open, close) in marker.pairs {
            guard let first = text.range(of: open),
                  let last = text.range(of: close, range: first.upperBound..<text.endIndex),
                  text.range(of: close, range: last.upperBound..<text.endIndex) == nil,
                  open == close || text.range(of: open, range: first.upperBound..<text.endIndex) == nil else { continue }
            let prefix = String(text[..<first.lowerBound]), content = String(text[first.upperBound..<last.lowerBound]), suffix = String(text[last.upperBound...])
            guard !content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, content.count <= 40,
                  !(prefix + content + suffix).contains("<"), !(prefix + content + suffix).contains(">") else { return nil }
            return Span(prefix: prefix, text: content, suffix: suffix)
        }
        return nil
    }

    private func project(_ span: Span) -> Range<Int>? {
        let n = characters.count, left = Array(span.prefix), right = Array(span.suffix)
        let before = Self.prefixCosts(left, characters)
        let after = Self.prefixCosts(Array(right.reversed()), Array(characters.reversed()))
        var ranges: [Range<Int>] = []
        if span.text.range(of: #"\p{Han}"#, options: .regularExpression) != nil {
            var position = target.startIndex
            let offsets = Dictionary(uniqueKeysWithValues: (Array(target.indices) + [target.endIndex]).enumerated().map { ($0.element, $0.offset) })
            while position < target.endIndex, let match = target.range(of: span.text, range: position..<target.endIndex) {
                if let a = offsets[match.lowerBound], let b = offsets[match.upperBound] { ranges.append(a..<b) }
                position = target.index(after: match.lowerBound)
            }
        }
        let exact = !ranges.isEmpty
        if !exact {
            // A retained English token or a synonym can still locate a word.
            // Require the marked hole to explain text missing from the two
            // surrounding strings, rather than inventing a word when it was omitted.
            let han = characters.map { character in character.unicodeScalars.allSatisfy { (0x3400...0x9fff).contains($0.value) || (0xf900...0xfaff).contains($0.value) } }
            for a in 0..<n {
                for b in (a + 1)...min(n, a + 16) {
                    if !han[b - 1] { break }
                    ranges.append(a..<b)
                }
            }
        }
        let emptyCost = (0...n).map { before[$0] + after[n - $0] }.min()!
        var best: (cost: Int, partial: Int, length: Int)?
        var candidates: [Range<Int>] = []
        var exactCosts: [Int] = []
        for range in ranges {
            let cost = before[range.lowerBound] + after[n - range.upperBound]
            guard cost <= max(6, max(n, left.count + right.count) / 2), exact || cost < emptyCost else { continue }
            let partial = (wordStarts.contains(range.lowerBound) ? 0 : 1) + (wordEnds.contains(range.upperBound) ? 0 : 1)
            let rank = (cost, partial, range.count)
            if exact { exactCosts.append(cost) }
            if best == nil || rank < best! { best = rank; candidates = [range] }
            else if rank == best! { candidates.append(range) }
        }
        let competing = exactCosts.sorted()
        if competing.count > 1, competing[1] - competing[0] <= 2 { return nil }
        guard candidates.count == 1, let result = candidates.first else { return nil }
        let prefix = Self.anchor(left, Array(characters[..<result.lowerBound]), left: true)
        let suffix = Self.anchor(right, Array(characters[result.upperBound...]), left: false)
        guard prefix + suffix >= 4, max(prefix, suffix) >= 3 || min(prefix, suffix) >= 2 else { return nil }
        return result
    }

    // Distances to every prefix let a marked span move slightly with Chinese
    // word order. The global position, nearby anchors and unique minimum keep
    // repeated words separate. Memory stays linear in the translated length.
    private static func prefixCosts(_ source: [Character], _ target: [Character]) -> [Int] {
        var row = Array(0...target.count)
        for (i, character) in source.enumerated() {
            var next = [i + 1]
            next.reserveCapacity(target.count + 1)
            for (j, other) in target.enumerated() {
                next.append(min(row[j + 1] + 1, next[j] + 1, row[j] + (character == other ? 0 : 1)))
            }
            row = next
        }
        return row
    }

    private static func anchor(_ source: [Character], _ target: [Character], left: Bool) -> Int {
        let a = source.filter { $0.isLetter || $0.isNumber }, b = target.filter { $0.isLetter || $0.isNumber }
        let x = Array(left ? a.suffix(24) : a.prefix(24)), y = Array(left ? b.suffix(24) : b.prefix(24))
        var row = Array(repeating: 0, count: y.count + 1), best = 0
        for (i, character) in x.enumerated() {
            var next = Array(repeating: 0, count: y.count + 1)
            for (j, other) in y.enumerated() where character == other {
                next[j + 1] = row[j] + 1
                let near = left ? x.count - i - 1 <= 8 && y.count - j - 1 <= 8 : i + 1 - next[j + 1] <= 8 && j + 1 - next[j + 1] <= 8
                if near { best = max(best, next[j + 1]) }
            }
            row = next
        }
        return best
    }
}
