import Foundation

// Completeness is independent of paragraph/list/title structure. It describes
// the evidence we captured, not a claim that an arbitrary sentence is grammatical.
enum ContextExtent: String, Codable, Hashable {
    case complete, missingStart, missingEnd, missingBoth, uncertain
    var notice: String {
        switch self {
        case .complete: return ""
        case .missingStart: return "句首可能缺失，当前显示可见片段。"
        case .missingEnd: return "句尾可能缺失，当前显示可见片段。"
        case .missingBoth: return "原文两端可能缺失，当前显示可见片段。"
        case .uncertain: return "尚不能确认原文完整，当前显示可见片段。"
        }
    }
}

// Layout -> logical block -> normalized source map -> sentence -> completeness.
// Never discard line boundaries before deciding whether they belong together.
enum ContextBoundary {
    enum Source { case editor, ocr }
    enum Kind { case prose, list, comment, title, path, code, empty }
    struct SourceSpan {
        let line: Int
        var range: NSRange
        let frame: CGRect
    }
    struct Join {
        let from: Int, to: Int
        let reason: String
    }
    struct Analysis {
        let context: String
        let hit: NSRange
        let pointerHit: NSRange
        let block: String
        let blockHit: NSRange
        let structure: Passage.Structure
        let extent: ContextExtent
        let sources: [SourceSpan]
        let joins: [Join]
    }
    private struct Line {
        let original: Int
        let text: String
        let hit: NSRange?
        let frame: CGRect // top-left coordinates inside the boundary pipeline
        let kind: Kind
        let indent: Int
        let content: String
        let contentOffset: Int
    }
    private enum Edge { case boundary, uncertain, clipped }
    private struct Block {
        let lines: [Line]
        let joins: [Join]
        let start, end: Edge
    }
    private struct Normalized {
        var text = ""
        var hit = NSRange(location: 0, length: 0)
        var sources: [SourceSpan] = []
        var wordSeams: [Int] = []
    }

    // OCR engines can split a single baseline into multiple observations.
    // Restore ordinary word gaps before looking for vertical neighbors; large
    // gutters and short independent column labels remain separate.
    static func coalesce(_ input: [TextLine], language: String? = nil) -> [TextLine] {
        let language = language ?? LanguageResolver.resolve(input.map(\.text).joined(separator: "\n"))
        var rows: [[TextLine]] = []
        for line in input.sorted(by: { $0.frame.midY > $1.frame.midY }) {
            if let row = rows.firstIndex(where: { row in
                let other = row[0].frame, height = max(other.height, line.frame.height)
                let overlap = min(other.maxY, line.frame.maxY) - max(other.minY, line.frame.minY)
                return abs(other.midY - line.frame.midY) <= height * 0.4 && overlap >= min(other.height, line.frame.height) * 0.6
            }) { rows[row].append(line) }
            else { rows.append([line]) }
        }
        return rows.flatMap { row -> [TextLine] in
            var result: [TextLine] = []
            for next in row.sorted(by: { $0.frame.minX < $1.frame.minX }) {
                guard let left = result.last else { result.append(next); continue }
                let height = max(left.frame.height, next.frame.height), gap = next.frame.minX - left.frame.maxX
                let a = left.text.trimmingCharacters(in: .whitespacesAndNewlines), b = next.text.trimmingCharacters(in: .whitespacesAndNewlines)
                let duplicate = gap < 0 ? overlappingWords(a, b) : nil
                let duplicateWidth = duplicate.map { left.frame.width * CGFloat($0.utf16.count) / CGFloat(max(1, a.utf16.count)) } ?? 0
                let overlappingObservation = duplicate != nil && -gap >= duplicateWidth * 0.35 && -gap <= duplicateWidth * 1.7 + height
                let independentLabels = a.split(whereSeparator: \.isWhitespace).count == 1 && b.split(whereSeparator: \.isWhitespace).count == 1 &&
                    !startsLowercase(b) && !continuationCue(a)
                guard (gap >= -0.4 * height && gap <= height && !independentLabels) || overlappingObservation else { result.append(next); continue }
                let prefix = left.text.replacingOccurrences(of: #"\s+$"#, with: "", options: .regularExpression)
                let leading = next.text.prefix(while: \.isWhitespace).utf16.count
                let duplicateLength = overlappingObservation ? duplicate!.utf16.count : 0
                let remainder = (b as NSString).substring(from: duplicateLength)
                let removedWhitespace = remainder.prefix(while: \.isWhitespace).utf16.count
                let tail = remainder.trimmingCharacters(in: .whitespacesAndNewlines)
                let separator = !tail.isEmpty && needsSpace(prefix.last, tail.first, language: language) ? " " : ""
                let text = prefix + separator + tail
                let hit = left.hit ?? next.hit.map { hit -> NSRange in
                    let position = hit.location - leading
                    let location = position < duplicateLength ? prefix.utf16.count - duplicateLength + position :
                        prefix.utf16.count + separator.utf16.count + position - duplicateLength - removedWhitespace
                    return NSRange(location: location, length: hit.length)
                }
                result[result.count - 1] = TextLine(text: text, frame: left.frame.union(next.frame), hit: hit)
            }
            return result
        }
    }

    private static func overlappingWords(_ left: String, _ right: String) -> String? {
        let words = left.split(whereSeparator: \.isWhitespace)
        for count in stride(from: words.count, through: 1, by: -1) {
            let candidate = words.suffix(count).joined(separator: " ")
            if right == candidate || right.hasPrefix(candidate + " ") { return candidate }
        }
        return nil
    }

    static func analyze(_ raw: [TextLine], source: Source, captureBounds: CGRect? = nil, language: String? = nil) throws -> Analysis {
        let input = source == .ocr ? coalesce(raw, language: language) : raw
        let lines = input.enumerated().map { index, line in
            let ocrComment = source == .ocr && corroboratedComment(index, in: input)
            let body = content(line.text, ocrComment: ocrComment)
            return Line(original: index, text: line.text, hit: line.hit,
                 frame: CGRect(x: line.frame.minX, y: -line.frame.maxY, width: line.frame.width, height: line.frame.height),
                 kind: body.text.isEmpty ? .empty : ocrComment ? .comment : kind(line.text), indent: indentation(line.text),
                 content: body.text, contentOffset: body.offset)
        }
        guard let anchor = lines.firstIndex(where: { $0.hit != nil }) else { throw ReaderError.noText }
        let bounds = captureBounds.map { CGRect(x: $0.minX, y: -$0.maxY, width: $0.width, height: $0.height) }
        let block = logicalBlock(lines, anchor: anchor, source: source, bounds: bounds)
        let blockLanguage = language ?? LanguageResolver.resolve(block.lines.map(\.content).joined(separator: "\n"))
        var normalized = normalize(block.lines, language: blockLanguage)
        guard normalized.hit.length > 0, Range(normalized.hit, in: normalized.text) != nil else { throw ReaderError.noText }
        let pointerHit = normalized.hit
        // Recover a word broken at a soft/hard hyphen. A hard hyphen is retained:
        // removing it without lexical evidence could change a genuine compound.
        for seam in normalized.wordSeams {
            let word = wordAcross(seam, in: normalized.text)
            if NSIntersectionRange(word, normalized.hit).length > 0 { normalized.hit = word }
        }
        let blockKind: Kind = block.lines.first?.kind == .list ? .list : lines[anchor].kind
        let unit: NSRange
        if [.title, .path, .code].contains(blockKind) {
            unit = NSRange(location: 0, length: normalized.text.utf16.count)
        } else {
            unit = sentenceRange(in: normalized.text, hit: normalized.hit, list: blockKind == .list)
        }
        guard let range = Range(unit, in: normalized.text) else { throw ReaderError.noText }
        let context = String(normalized.text[range])
        let hit = NSRange(location: normalized.hit.location - unit.location, length: normalized.hit.length)
        let sourceSpans = normalized.sources.compactMap { span -> SourceSpan? in
            let overlap = NSIntersectionRange(span.range, unit)
            guard overlap.length > 0 else { return nil }
            return SourceSpan(line: span.line, range: NSRange(location: overlap.location - unit.location, length: overlap.length), frame: span.frame)
        }
        var structure: Passage.Structure = blockKind == .list ? .list : blockKind == .title ? .title : blockKind == .path ? .path : blockKind == .code ? .code : .sentence
        if structure == .sentence && (startsEllipsis(context) || endsEllipsis(context)) { structure = .fragment }
        var start = unit.location == 0 ? block.start : .boundary
        if unit.location == 0, start == .boundary, source == .ocr, let first = block.lines.first,
           first.kind != .comment, !matches(commentVariant, in: first.text).isEmpty { start = .uncertain }
        let end: Edge = NSMaxRange(unit) < normalized.text.utf16.count ? .boundary : block.end
        let extent = completeness(context, structure: structure, unit: unit, blockLength: normalized.text.utf16.count,
                                  sources: sourceSpans, bounds: bounds,
                                  standalone: hit.location == 0 && hit.length == context.utf16.count, start: start, end: end)
        return Analysis(context: context, hit: hit, pointerHit: NSRange(location: pointerHit.location - unit.location, length: pointerHit.length), block: normalized.text, blockHit: normalized.hit,
                        structure: structure, extent: extent, sources: sourceSpans, joins: block.joins)
    }

    static func editorLines(_ text: String, selection: NSRange) throws -> [TextLine] {
        guard Range(selection, in: text) != nil else { throw ReaderError.noText }
        var offset = 0
        return text.components(separatedBy: "\n").enumerated().map { index, line in
            defer { offset += line.utf16.count + 1 }
            let span = NSRange(location: offset, length: line.utf16.count)
            let overlap = NSIntersectionRange(span, selection)
            let hit = overlap.length > 0 ? NSRange(location: overlap.location - offset, length: overlap.length) : nil
            return TextLine(text: line, frame: CGRect(x: 0, y: -index * 25 - 18, width: max(1, line.count * 9), height: 18), hit: hit)
        }
    }

    static func evidence(_ text: String, selection: NSRange) throws -> (text: String, selection: NSRange) {
        let analysis = try analyze(editorLines(text, selection: selection), source: .editor)
        return (analysis.block, analysis.blockHit)
    }

    private static func logicalBlock(_ lines: [Line], anchor: Int, source: Source, bounds: CGRect?) -> Block {
        guard ![.empty, .title, .path, .code].contains(lines[anchor].kind) else { return Block(lines: [lines[anchor]], joins: [], start: .boundary, end: .boundary) }
        var before: [Int] = [], after: [Int] = [], decisions: [Join] = []
        var start = Edge.boundary, end = Edge.boundary
        func neighbor(_ index: Int, direction: Int) -> Int? {
            if source == .editor { return lines.indices.contains(index + direction) ? index + direction : nil }
            let current = lines[index].frame
            return lines.indices.filter { i in
                let rect = lines[i].frame, height = max(current.height, rect.height)
                let step = CGFloat(direction) * (rect.midY - current.midY)
                let overlap = min(current.maxX, rect.maxX) - max(current.minX, rect.minX)
                return step >= 0.45 * min(current.height, rect.height) && step <= 3.2 * height &&
                    overlap >= 0.25 * min(current.width, rect.width) && abs(rect.minX - current.minX) <= 3.5 * height
            }.min { a, b in
                let ra = lines[a].frame, rb = lines[b].frame
                return abs(ra.midY - current.midY) + 0.15 * abs(ra.minX - current.minX) <
                       abs(rb.midY - current.midY) + 0.15 * abs(rb.minX - current.minX)
            }
        }
        func hasParagraphSpacing(after left: Int, before right: Int) -> Bool {
            let a = lines[left], b = lines[right], height = max(a.frame.height, b.frame.height)
            let spacing = b.frame.midY - a.frame.midY
            guard source == .ocr, spacing > 1.5 * height, terminal(a.content, followedBy: b.content),
                  let previous = neighbor(left, direction: -1) else { return false }
            let prior = lines[previous].frame
            // Compare the gap after a short final row with the preceding body-line pitch.
            return abs(prior.minX - a.frame.minX) <= height && prior.maxX - a.frame.maxX > 2 * height &&
                spacing > (a.frame.midY - prior.midY) + 0.5 * height
        }
        for direction in [-1, 1] {
            var current = anchor
            while let next = neighbor(current, direction: direction) {
                let left = direction < 0 ? next : current, right = direction < 0 ? current : next
                guard let reason = joinReason(lines[left], lines[right], source: source) else {
                    if !hardBoundary(lines[left], lines[right], source: source) {
                        if direction < 0 { start = .uncertain } else { end = .uncertain }
                    }
                    break
                }
                if hasParagraphSpacing(after: left, before: right) { break }
                // A cropped end of one row and the beginning of the next are not
                // contiguous text. Keep the side containing the actual pointer.
                if let bounds, (bounds.maxX - lines[left].frame.maxX <= lines[left].frame.height * 0.45 ||
                                lines[right].frame.minX - bounds.minX <= lines[right].frame.height * 0.45),
                   !terminal(lines[left].content, followedBy: lines[right].content) {
                    if direction < 0 { start = .clipped } else { end = .clipped }
                    break
                }
                decisions.append(Join(from: lines[left].original, to: lines[right].original, reason: reason))
                if direction < 0 { before.append(next) } else { after.append(next) }
                current = next
            }
        }
        return Block(lines: (before.reversed() + [anchor] + after).map { lines[$0] }, joins: decisions,
                     start: start, end: end)
    }

    private static func hardBoundary(_ left: Line, _ right: Line, source: Source) -> Bool {
        if [.empty, .title, .path, .code].contains(left.kind) || [.empty, .title, .path, .code, .list].contains(right.kind) { return true }
        if (left.kind == .comment) != (right.kind == .comment) { return true }
        let a = left.content, b = right.content
        if terminal(a, followedBy: b) { return true }
        if source == .editor { return right.indent > left.indent && !continuationCue(a) }
        let height = max(left.frame.height, right.frame.height)
        return max(left.frame.height, right.frame.height) > min(left.frame.height, right.frame.height) * 1.6 ||
            right.frame.midY - left.frame.midY > 2.05 * height ||
            (right.frame.minX - left.frame.minX >= height && !continuationCue(a) && !startsLowercase(b))
    }

    private static func joinReason(_ left: Line, _ right: Line, source: Source) -> String? {
        if left.kind == .empty || right.kind == .empty { return nil }
        if [.title, .path, .code].contains(left.kind) || [.title, .path, .code].contains(right.kind) { return nil }
        if (left.kind == .comment) != (right.kind == .comment) { return nil }
        if right.kind == .list { return nil }
        let a = left.content, b = right.content
        if a.isEmpty || b.isEmpty { return nil }
        let ends = terminal(a, followedBy: b)
        let continuation = continuationCue(a) || startsLowercase(b) || (!ends && a.last == ".")
        if left.kind == .list {
            let indented = source == .editor ? right.indent >= listIndent(left.text) : right.frame.minX > left.frame.minX + left.frame.height * 0.45
            return indented || (!ends && continuation) ? "list-continuation" : nil
        }
        if source == .editor {
            if left.kind == .comment { return "comment-continuation" }
            if ends { return nil } // an explicit newline after a full sentence is a paragraph boundary
            if right.indent > left.indent && !continuationCue(a) { return nil }
            if continuation || (containsUncasedScript(a) && containsUncasedScript(b) && a.count >= 8) { return "text-continuation" }
            return nil // a hard newline without continuation evidence is not silently erased
        }
        let height = max(left.frame.height, right.frame.height)
        if max(left.frame.height, right.frame.height) > min(left.frame.height, right.frame.height) * 1.6 { return nil }
        if right.frame.midY - left.frame.midY > 2.05 * height { return nil }
        if left.kind == .comment { return "comment-continuation" }
        // Missing OCR punctuation must not turn a new subject/clause into the
        // tail of the previous sentence. Keep this boundary explicitly uncertain.
        if !ends && !continuationCue(a) && sentenceOpening(b) { return nil }
        if right.frame.minX - left.frame.minX >= height && !continuationCue(a) && !startsLowercase(b) { return nil }
        let short = a.split(whereSeparator: \.isWhitespace).count <= 3 && !containsJoinedScript(a)
        if short && !ends && !continuation { return nil }
        if containsJoinedScript(a), a.count < 8, !continuationCue(a), !ends { return nil }
        return continuation ? "layout-and-language" : "same-column-flow"
    }

    private static func normalize(_ lines: [Line], language: String) -> Normalized {
        var result = Normalized()
        for line in lines {
            let clean = line.content
            let leading = line.contentOffset
            if !result.text.isEmpty {
                if result.text.last == "\u{00ad}" {
                    result.text.removeLast()
                    if let last = result.sources.indices.last { result.sources[last].range.length -= 1 }
                    result.wordSeams.append(result.text.utf16.count)
                } else if result.text.last == "-" || result.text.last == "‐" {
                    result.wordSeams.append(result.text.utf16.count)
                } else if needsSpace(result.text.last, clean.first, language: language) { result.text += " " }
            }
            let offset = result.text.utf16.count
            if let hit = line.hit { result.hit = NSRange(location: offset + hit.location - leading, length: hit.length) }
            result.sources.append(SourceSpan(line: line.original, range: NSRange(location: offset, length: clean.utf16.count), frame: line.frame))
            result.text += clean
        }
        return result
    }

    private static func wordAcross(_ seam: Int, in text: String) -> NSRange {
        let value = text as NSString
        func word(_ n: Int) -> Bool {
            guard n >= 0, n < value.length, let scalar = UnicodeScalar(value.character(at: n)) else { return false }
            return CharacterSet.alphanumerics.contains(scalar) || "-'’‐".unicodeScalars.contains(scalar)
        }
        var left = seam, right = seam
        while word(left - 1) { left -= 1 }
        while word(right) { right += 1 }
        return NSRange(location: left, length: right - left)
    }

    // Both platforms use this contract: punctuation first respects URLs,
    // decimals, initials/abbreviations and balanced delimiters/attribution.
    static func sentenceRange(in text: String, hit: NSRange, list: Bool = false) -> NSRange {
        let chars = Array(text)
        var offsets = [0]
        for c in chars { offsets.append(offsets.last! + String(c).utf16.count) }
        let protected = matches(#"(?:https?://|www\.)\S+|[\p{L}\p{N}._%+-]+@[\p{L}\p{N}.-]+\.[\p{L}]{2,}"#, in: text).map { match -> NSRange in
            var range = match
            while range.length > 0, let r = Range(range, in: text), let last = text[r].last, ".!?。！？,;".contains(last) { range.length -= String(last).utf16.count }
            return range
        }
        let prefix = list ? matches(#"^\s*(?:[•●▪◦*+-]|[0-9]+[.)、])\s*"#, in: text).first : nil
        var stack: [Character] = [], start = 0, i = 0
        while i < chars.count {
            let c = chars[i]
            if let closing = closer(c), !apostrophe(chars, i) {
                if stack.last == c { stack.removeLast() } else { stack.append(closing) }
            } else if stack.last == c { stack.removeLast() }
            if ".!?。！？．".contains(c), !protected.contains(where: { NSLocationInRange(offsets[i], $0) }),
               !(prefix.map { NSLocationInRange(offsets[i], $0) } ?? false), punctuationEnds(chars, at: i) {
                var end = i + 1, rest = stack
                while end < chars.count && ".!?。！？．".contains(chars[end]) { end += 1 }
                while end < chars.count && isClosing(chars[end]) {
                    if rest.last == chars[end] { rest.removeLast() }
                    end += 1
                }
                var next = end
                while next < chars.count && chars[next].isWhitespace { next += 1 }
                let quotedContinuation = !stack.isEmpty && next < chars.count &&
                    (chars[next].isLowercase || containsJoinedScript(String(chars[next])) || ",，:：;；".contains(chars[next]))
                if rest.isEmpty && !quotedContinuation {
                    let candidate = trimmedRange(chars, start: start, end: end, offsets: offsets)
                    if NSIntersectionRange(candidate, hit).length == hit.length { return candidate }
                    start = next; i = next; stack = []; continue
                }
            }
            i += 1
        }
        return trimmedRange(chars, start: start, end: chars.count, offsets: offsets)
    }

    private static func punctuationEnds(_ chars: [Character], at i: Int) -> Bool {
        let c = chars[i]
        if "。！？!?".contains(c) { return true }
        if i > 0 && i + 1 < chars.count && chars[i - 1].isNumber && chars[i + 1].isNumber { return false }
        if i + 1 < chars.count && chars[i + 1] == "." { return false }
        if i + 1 < chars.count && chars[i + 1].isLetter { return false }
        var left = i
        while left > 0 && (chars[left - 1].isLetter || chars[left - 1] == ".") { left -= 1 }
        let token = String(chars[left..<i]).lowercased()
        var next = i + 1
        while next < chars.count && (chars[next].isWhitespace || isClosing(chars[next])) { next += 1 }
        if next == chars.count { return !honorifics.contains(token) && !["e.g", "i.e"].contains(token) }
        if honorifics.contains(token) || token.count == 1 && token.first?.isLetter == true { return false }
        if abbreviations.contains(token) || token.range(of: #"^(?:[a-z]\.)+[a-z]$"#, options: .regularExpression) != nil {
            let rest = String(chars[next...]).split(whereSeparator: { !$0.isLetter }).first.map(String.init) ?? ""
            return sentenceStarters.contains(rest)
        }
        return true
    }

    private static func completeness(_ text: String, structure: Passage.Structure, unit: NSRange, blockLength: Int,
                                     sources: [SourceSpan], bounds: CGRect?, standalone: Bool, start: Edge, end: Edge) -> ContextExtent {
        if [.title, .path, .code].contains(structure) { return .complete }
        var missingStart = start == .clipped || startsEllipsis(text), missingEnd = end == .clipped || endsEllipsis(text)
        if let bounds, let first = sources.first, let last = sources.last {
            if unit.location == 0 {
                missingStart = missingStart || first.frame.minY - bounds.minY <= first.frame.height * 1.2 || first.frame.minX - bounds.minX <= first.frame.height * 0.45
            }
            if NSMaxRange(unit) == blockLength && !terminal(text) {
                missingEnd = missingEnd || bounds.maxY - last.frame.maxY <= last.frame.height * 1.2 || bounds.maxX - last.frame.maxX <= last.frame.height * 0.45
            }
        }
        missingEnd = missingEnd || hasUnclosedDelimiter(text) || dangling(text)
        if missingStart && missingEnd { return .missingBoth }
        if missingStart { return .missingStart }
        if missingEnd { return .missingEnd }
        let uncertainBoundary = start == .uncertain || end == .uncertain
        if standalone && !uncertainBoundary { return .complete }
        if uncertainBoundary || !terminal(text) || (unit.location == 0 && startsLowercase(text)) { return .uncertain }
        return .complete
    }

    private static func hasUnclosedDelimiter(_ text: String) -> Bool {
        let chars = Array(text)
        var stack: [Character] = []
        for (i, c) in chars.enumerated() {
            if apostrophe(chars, i) { continue }
            if let closing = closer(c) {
                if stack.last == c { stack.removeLast() } else { stack.append(closing) }
            } else if stack.last == c { stack.removeLast() }
        }
        return !stack.isEmpty
    }
    private static func closer(_ c: Character) -> Character? {
        ["(": ")", "[": "]", "{": "}", "（": "）", "【": "】", "「": "」", "『": "』", "“": "”", "‘": "’", "«": "»", "\"": "\"", "'": "'"][c]
    }
    private static func isClosing(_ c: Character) -> Bool { ")]}）】」』”’»\"'".contains(c) }
    private static func apostrophe(_ chars: [Character], _ i: Int) -> Bool {
        "'’".contains(chars[i]) && i > 0 && i + 1 < chars.count && chars[i - 1].isLetter && chars[i + 1].isLetter
    }
    private static func trimmedRange(_ chars: [Character], start: Int, end: Int, offsets: [Int]) -> NSRange {
        var a = start, b = end
        while a < b && chars[a].isWhitespace { a += 1 }
        while b > a && chars[b - 1].isWhitespace { b -= 1 }
        return NSRange(location: offsets[a], length: offsets[b] - offsets[a])
    }
    private static func startsEllipsis(_ text: String) -> Bool { text.hasPrefix("…") || text.hasPrefix("...") }
    private static func endsEllipsis(_ text: String) -> Bool { text.hasSuffix("…") || text.hasSuffix("...") }
    private static func terminal(_ text: String, followedBy next: String? = nil) -> Bool {
        let chars = Array(text.trimmingCharacters(in: .whitespacesAndNewlines))
        var i = chars.count - 1
        while i >= 0 && isClosing(chars[i]) { i -= 1 }
        guard i >= 0, ".!?。！？．".contains(chars[i]) else { return false }
        return punctuationEnds(chars + Array(next.map { " " + $0 } ?? ""), at: i)
    }
    private static func startsLowercase(_ text: String) -> Bool {
        text.first(where: \.isLetter)?.isLowercase == true
    }
    private static func sentenceOpening(_ text: String) -> Bool {
        let first = text.split(whereSeparator: { !$0.isLetter }).first.map(String.init) ?? ""
        return sentenceStarters.contains(first) || !matches(#"^[A-Z][\p{L}'’-]+(?:\s+[\p{L}'’-]+){0,2}\s+(?:is|are|was|were|has|have|had|will|would|can|could|should|does|do|did)\b"#, in: text).isEmpty
    }
    private static func dangling(_ text: String) -> Bool {
        if let last = text.last, ",，:：;；-‐".contains(last) { return true }
        let last = text.split(whereSeparator: { !$0.isLetter }).last.map { String($0).lowercased() } ?? ""
        return danglingWords.contains(last)
    }
    private static func continuationCue(_ text: String) -> Bool {
        if let last = text.last, ",，:：;；-‐\u{00ad}".contains(last) { return true }
        if !terminal(text), containsUncasedScript(text), continuations.contains(where: text.hasSuffix) { return true }
        return dangling(text) || hasUnclosedDelimiter(text)
    }
    private static func containsJoinedScript(_ text: String) -> Bool {
        text.range(of: #"[\p{Han}\p{Hiragana}\p{Katakana}]"#, options: .regularExpression) != nil
    }
    private static func containsUncasedScript(_ text: String) -> Bool {
        containsJoinedScript(text) || text.range(of: #"[\p{Hangul}]"#, options: .regularExpression) != nil
    }
    private static func needsSpace(_ left: Character?, _ right: Character?, language: String) -> Bool {
        guard let left, let right else { return false }
        if (language.hasPrefix("zh") || language.hasPrefix("ja")) && (containsJoinedScript(String(left)) || containsJoinedScript(String(right))) { return false }
        return !(containsJoinedScript(String(left)) && containsJoinedScript(String(right))) &&
            !("、。，；：！？".contains(left) && containsJoinedScript(String(right))) &&
            !"、。，；：！？「」『』）】".contains(right) && !"（【「『".contains(left)
    }
    private static func indentation(_ text: String) -> Int { text.prefix(while: \.isWhitespace).reduce(0) { $0 + ($1 == "\t" ? 4 : 1) } }
    private static func listIndent(_ text: String) -> Int {
        guard let range = matches(#"^\s*(?:[•●▪◦*+-]|[0-9]+[.)、])\s*"#, in: text).first else { return 0 }
        return range.length
    }
    private static func cleaned(_ text: String) -> String {
        content(text).text
    }
    private static func content(_ text: String, ocrComment: Bool = false) -> (text: String, offset: Int) {
        let prefix = matches(ocrComment ? commentVariant : #"^\s*//[/!]?(?:\s+|$)"#, in: text).first?.length ?? 0
        let remainder = (text as NSString).substring(from: prefix)
        let leading = remainder.prefix(while: \.isWhitespace).utf16.count
        return (remainder.trimmingCharacters(in: .whitespacesAndNewlines), prefix + leading)
    }
    private static let commentVariant = #"^\s*(?://[/!]?|/|[|Il/]{2})(?:\s+|$)"#
    private static func corroboratedComment(_ index: Int, in lines: [TextLine]) -> Bool {
        guard !matches(commentVariant, in: lines[index].text).isEmpty else { return false }
        if kind(lines[index].text) == .comment { return true }
        guard content(lines[index].text, ocrComment: true).text.split(whereSeparator: \.isWhitespace).count >= 3 else { return false }
        let frame = lines[index].frame
        return lines.indices.contains { i in
            guard i != index else { return false }
            let next = lines[i].frame, height = max(frame.height, next.height)
            return abs(frame.minX - next.minX) <= height * 2 && abs(frame.midY - next.midY) <= height * 2.1 &&
                (kind(lines[i].text) == .code || !matches(commentVariant, in: lines[i].text).isEmpty)
        }
    }
    private static func kind(_ text: String) -> Kind {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if cleaned(text).isEmpty { return .empty }
        if !matches(#"^\s*//[/!]?(?:\s+|$)"#, in: text).isEmpty { return .comment }
        if !matches(#"^#{1,6}\s+"#, in: trimmed).isEmpty { return .title }
        if !matches(#"^(?:[A-Za-z]:)?[\w./\\-]+[/\\][\w.\-]+$"#, in: trimmed).isEmpty { return .path }
        if !matches(#"^(?:[•●▪◦*+-]|[0-9]+[.)、])\s+"#, in: trimmed).isEmpty { return .list }
        if !matches(#"^(?:(?:type|func|struct|class|enum|import|package|return|let|var|const|def|fn|public|private)\b|[{}]\s*$|[A-Za-z_][\w.\[\]]*\s*(?::=|=(?!=)))"#, in: trimmed).isEmpty { return .code }
        if !matches(#"^[A-Za-z_]\w*\s+(?:string|int|bool|float\d*|[A-Za-z_]\w*\.[A-Za-z_]\w*)\s*(?:`[^`]*`)?;?$"#, in: trimmed).isEmpty { return .code }
        return .prose
    }
    private static func matches(_ pattern: String, in text: String) -> [NSRange] {
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return [] }
        return regex.matches(in: text, range: NSRange(text.startIndex..., in: text)).map(\.range)
    }
    private static let honorifics: Set<String> = ["dr", "prof", "mr", "mrs", "ms", "fig", "eq", "no", "sr", "jr"]
    private static let abbreviations: Set<String> = ["e.g", "i.e", "etc", "vs", "inc", "ltd", "st", "approx", "dept", "vol"]
    private static let sentenceStarters: Set<String> = ["The", "A", "An", "This", "That", "These", "Those", "He", "She", "It", "They", "We", "I", "You", "However", "Meanwhile", "Therefore", "Another"]
    private static let danglingWords: Set<String> = ["the", "a", "an", "and", "or", "but", "because", "although", "unless", "until", "while", "that", "which", "whose", "when", "where", "whether", "of", "to", "from", "with", "without", "for", "on", "at", "by", "as", "into", "between", "through", "than", "not", "is", "are", "was", "were", "le", "la", "les", "de", "du", "et", "der", "die", "das", "und", "el", "los", "las", "del", "以及", "因为", "如果", "虽然", "以便"]
    private static let continuations = ["の", "を", "は", "が", "に", "と", "で", "へ", "も", "から", "まで", "的", "在", "与", "和", "将", "把", "被", "向", "从", "对", "为", "由", "及", "或", "은", "는", "이", "가", "을", "를", "의", "에", "와", "과", "도", "로"]
}

// One bounded retry may recover text just outside the first capture. This
// orchestration is shared by the real capture path and cancellation/error tests.
enum ContextCapture {
    static func complete(_ first: Passage, expanded: () async throws -> Passage) async throws -> Passage {
        try Task.checkCancellation()
        guard first.needsContextExpansion else { return first }
        do {
            let next = try await expanded()
            try Task.checkCancellation()
            func pointedWord(_ value: Passage) -> String {
                guard let anchor = value.anchor, let range = Range(anchor, in: value.context) else { return value.text.lowercased() }
                return String(value.context[range]).lowercased()
            }
            guard pointedWord(first) == pointedWord(next) else { return first }
            return next.hasCompleteContext || next.context.count >= first.context.count ? next : first
        } catch {
            try Task.checkCancellation()
            if error is CancellationError { throw error }
            return first // a failed optional retry must not erase the visible original
        }
    }
}
