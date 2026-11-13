import Foundation

// The original pointer remains the anchor. Only whole English words on the
// same side of punctuation can form a new query.
struct PhraseRangeChoice: Identifiable {
    let range: NSRange
    let action: String
    let text: String
    var id: NSRange { range }
}

extension Passage {
    private static let englishWord = try! NSRegularExpression(
        pattern: #"(?<![A-Za-z0-9_/‐‑-])(?<![A-Za-z0-9_]\.)[A-Za-z]+(?:['’‐‑-][A-Za-z]+)*(?![A-Za-z0-9_/‐‑-]|\.[A-Za-z0-9_])"#)

    var phraseRangeChoices: [PhraseRangeChoice] {
        guard structure != .path, structure != .code, headwordLanguage == "en",
              let selection, let anchor, anchor.length > 0, NSIntersectionRange(selection, anchor) == anchor
        else { return [] }
        let raw = context as NSString
        let words = Self.englishWord.matches(in: context, range: NSRange(location: 0, length: raw.length)).map(\.range)
        guard let first = words.firstIndex(where: { $0.location == selection.location }),
              let last = words.firstIndex(where: { NSMaxRange($0) == NSMaxRange(selection) }),
              first <= last, words[first...last].contains(anchor) else { return [] }
        func joined(_ left: NSRange, _ right: NSRange) -> Bool {
            let gap = NSRange(location: NSMaxRange(left), length: right.location - NSMaxRange(left))
            return gap.length > 0 && raw.substring(with: gap).rangeOfCharacter(from: CharacterSet.whitespaces.inverted) == nil
        }
        guard (first..<last).allSatisfy({ joined(words[$0], words[$0+1]) }) else { return [] }
        var choices: [PhraseRangeChoice] = []
        func append(_ action: String, _ range: NSRange) {
            choices.append(PhraseRangeChoice(range: range, action: action, text: raw.substring(with: range)))
        }
        if selection != anchor { append("只查指向的词", anchor) }
        if first > 0, joined(words[first-1], words[first]) {
            append("包含左词", NSUnionRange(words[first-1], selection))
        }
        if last+1 < words.count, joined(words[last], words[last+1]) {
            append("包含右词", NSUnionRange(selection, words[last+1]))
        }
        return choices
    }
}

// One immutable source/selection drives rendering and clicks. The view never
// searches again for the first occurrence of a repeated term.
struct CardContextContent {
    let original: Passage
    let expanded: Bool
    private var excerpt: SentenceExcerpt { SentenceExcerpt(original) }
    var passage: Passage { expanded ? original : excerpt.passage }
    private var offset: Int { (original.selection?.location ?? 0) - (passage.selection?.location ?? 0) }

    var text: AttributedString {
        var value = LookupTranslation.markedSentence(passage) ?? AttributedString(passage.context)
        let leading = !expanded && excerpt.isTruncated && offset > 0
        if leading { value = AttributedString("…") + value }
        if !expanded && excerpt.isTruncated && offset + passage.context.utf16.count < original.context.utf16.count { value += AttributedString("…") }
        guard LookupPolicy(original).isChineseContext else { return value }
        let regex = try! NSRegularExpression(pattern: "[A-Za-z][A-Za-z0-9+#]*")
        for match in regex.matches(in: passage.context, range: NSRange(passage.context.startIndex..., in: passage.context)) {
            let global = NSRange(location: match.range.location + offset, length: match.range.length)
            guard original.selection.map({ NSIntersectionRange($0, global).length == 0 }) ?? true,
                  let span = Range(NSRange(location: match.range.location + (leading ? 1 : 0), length: match.range.length), in: value) else { continue }
            value[span].link = URL(string: "waxterm://term/\(global.location)/\(global.length)")
        }
        return value
    }

    func selection(for url: URL) -> Passage? {
        guard url.scheme == "waxterm", url.host == "term" else { return nil }
        let pieces = url.path.split(separator: "/")
        guard pieces.count == 2, let location = Int(pieces[0]), let length = Int(pieces[1]), location >= 0, length > 0 else { return nil }
        return original.selecting(NSRange(location: location, length: length))
    }
}

// Used by the actual card and exercised without moving the user's mouse.
// Scope changes invalidate both success and failure from an older request.
struct CardContextTranslation {
    private(set) var request: TranslationRequest?
    private var activeID: UUID?
    private(set) var visible = false
    private(set) var error = ""

    mutating func begin(_ passage: Passage) {
        let next = TranslationRequest(text: passage.context, source: passage.sourceLanguage)
        request = next; activeID = next.id; visible = true; error = ""
    }
    mutating func cancel() { request = nil; activeID = nil; visible = false; error = "" }
    mutating func complete(_ completed: TranslationRequest, outcome: Result<String, Error>) -> String? {
        guard visible, activeID == completed.id, request?.id == completed.id else { return nil }
        request = nil; activeID = nil
        switch outcome {
        case .success(let output): return TranslationOutput.normalize(output, target: completed.target)
        case .failure: error = "这段原文翻译未完成，请检查本机语言包后重试。"; return nil
        }
    }
}
