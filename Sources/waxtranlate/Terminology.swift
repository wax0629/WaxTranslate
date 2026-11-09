import Foundation

struct TermMeaning {
    let label: String
    let meaning: String
    let kind: String
}

enum LocalTerminology {
    private struct Glossary: Decodable {
        let acronyms: [String: [String]]
        let names: [String: [String]]
        let contextNames: [String: [String]]
        let senses: [String: [[String]]]
        let multiple: [String: String]
        let lowercaseCues: [String: String]
    }
    private static let glossary: Glossary? = {
        let url: URL?
        if Bundle.main.bundleURL.pathExtension == "app" {
            url = Bundle.main.url(forResource: "reading-terms", withExtension: "json")
        } else {
            url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
                .deletingLastPathComponent().appendingPathComponent("Assets/Lexicon/reading-terms.json")
        }
        guard let url, let data = try? Data(contentsOf: url) else { return nil }
        return try? JSONDecoder().decode(Glossary.self, from: data)
    }()

    static func hasUnambiguousSpelling(_ word: String) -> Bool {
        guard let glossary else { return false }
        return glossary.names[word.lowercased()] != nil || ["mvp", "prd", "codex"].contains(word.lowercased()) ||
            (word == word.uppercased() && glossary.acronyms[word] != nil)
    }

    static func lookup(_ passage: Passage) -> TermMeaning? {
        guard passage.sourceLanguage == "en", !passage.isPhrase, passage.selection != nil,
              passage.text.count <= 100, let glossary else { return nil }
        var word = passage.text.precomposedStringWithCompatibilityMapping
            .replacingOccurrences(of: "['’]s$", with: "", options: [.regularExpression, .caseInsensitive])
        if word.range(of: "^[A-Z]{2,10}s$", options: .regularExpression) != nil { word.removeLast() }
        let key = word.lowercased()
        let clause = localClause(passage)
        var acronym = glossary.acronyms[word.uppercased()]
        if let cue = glossary.lowercaseCues[key], word != word.uppercased(), !matches(cue, in: clause) { acronym = nil }
        let senses = glossary.senses[key] ?? []
        let matching = senses.filter { $0.count == 3 && matches("\\b(?:" + $0[2] + ")\\b", in: clause) }
        let localSense = matching.count == 1 ? matching[0] : nil
        if let definition = writtenDefinition(passage, word: word) {
            let options = (acronym.map { [$0] } ?? []) + senses
            let known = options.first { initialWords($0[0]) == initialWords(definition.value) }
            if !definition.direct, let localSense, let known, known[0] != localSense[0] {
                return TermMeaning(label: "术语参考", meaning: format(localSense), kind: "缩写")
            }
            return TermMeaning(label: "文中定义", meaning: known.map(format) ?? definition.value,
                               kind: definition.acronym ? "缩写" : "文中用语")
        }
        if !senses.isEmpty {
            return TermMeaning(label: localSense == nil ? "多义参考" : "术语参考",
                meaning: localSense.map(format) ?? glossary.multiple[key] ?? word, kind: key == "codex" ? "名称" : "缩写")
        }
        if let acronym { return TermMeaning(label: "术语参考", meaning: format(acronym), kind: "缩写") }
        if let item = glossary.contextNames[key], item.count == 3, matches("\\b(?:" + item[0] + ")\\b", in: clause) {
            return TermMeaning(label: "术语参考", meaning: item[2], kind: item[1])
        }
        let nameKey = matches("^ciallo{2,6}$", in: key) ? "ciallo" : key
        if let item = glossary.names[nameKey], item.count == 2 { return TermMeaning(label: "术语参考", meaning: item[1], kind: item[0]) }
        return nil
    }

    private static func format(_ item: [String]) -> String {
        guard item.count >= 2 else { return "" }
        let gloss = item[1]
        if let comma = gloss.firstIndex(of: "，") {
            return String(gloss[..<comma]) + "（" + item[0] + "）" + String(gloss[comma...])
        }
        return gloss.trimmingCharacters(in: CharacterSet(charactersIn: "。")) + "（" + item[0] + "）。"
    }

    private static func localClause(_ passage: Passage) -> String {
        guard let selection = passage.selection, let range = Range(selection, in: passage.context) else { return passage.context.lowercased() }
        let pattern = "[,;!?]|\\b(?:whereas|while|but|" + NSRegularExpression.escapedPattern(for: passage.text) + ")\\b"
        let before = String(passage.context[..<range.lowerBound])
        let after = String(passage.context[range.upperBound...])
        let left = before.components(separatedByRegex: pattern).last ?? ""
        let right = after.components(separatedByRegex: pattern).first ?? ""
        return (String(left.suffix(110)) + passage.text + String(right.prefix(110))).lowercased()
    }

    private static func initialWords(_ text: String) -> [String] {
        text.lowercased().components(separatedBy: CharacterSet.alphanumerics.inverted).filter { !$0.isEmpty }
    }
    private static func initialsMatch(_ phrase: String, word: String) -> Bool {
        let words = initialWords(phrase)
        let letters = Array(word.lowercased())
        guard words.count >= 2, words.count <= letters.count + 4, words.first?.first == letters.first else { return false }
        let connectors = Set(["and", "for", "in", "of", "on", "the", "to", "with"])
        guard let last = words.last, !connectors.contains(last) else { return false }
        var positions: Set<Int> = [0]
        for word in words {
            let next = Set(positions.compactMap { $0 < letters.count && word.first == letters[$0] ? $0 + 1 : nil })
            positions = connectors.contains(word) ? positions.union(next) : next
        }
        return positions.contains(letters.count)
    }

    private static func writtenDefinition(_ passage: Passage, word: String) -> (value: String, direct: Bool, acronym: Bool)? {
        let text = passage.nearbyContext ?? passage.context
        let selected = passage.nearbySelection ?? passage.selection
        let pattern = "(?<![\\w])" + NSRegularExpression.escapedPattern(for: passage.text) + "(?![\\w])"
        guard let regex = try? NSRegularExpression(pattern: pattern, options: .caseInsensitive) else { return nil }
        var definitions: [(String, Bool, Bool)] = []
        for match in regex.matches(in: text, range: NSRange(text.startIndex..., in: text)) {
            guard let range = Range(match.range, in: text) else { continue }
            let before = String(text[..<range.lowerBound])
            let after = String(text[range.upperBound...]).trimmingCharacters(in: .whitespaces)
            let direct = match.range == selected
            var expansion: String?
            if before.last == "(" || before.last == "（", after.first == ")" || after.first == "）" {
                let tail = String(before.dropLast()).components(separatedByRegex: "[^A-Za-z0-9\\s-]").last ?? ""
                let words = tail.split(whereSeparator: { $0.isWhitespace })
                for index in words.indices.reversed() {
                    let candidate = words[index...].joined(separator: " ")
                    if initialsMatch(candidate, word: word) { expansion = candidate; break }
                }
            } else if after.first == "(" || after.first == "（", let end = after.firstIndex(where: { $0 == ")" || $0 == "）" }) {
                let candidate = String(after[after.index(after.startIndex, offsetBy: 1)..<end])
                if initialsMatch(candidate, word: word) { expansion = candidate }
            } else if let lead = after.range(of: "^(?:stands? for|is short for|is an abbreviation for)\\s+", options: [.regularExpression, .caseInsensitive]) {
                let words = String(after[lead.upperBound...]).components(separatedByRegex: "[^A-Za-z0-9\\s-]")[0].split(whereSeparator: { $0.isWhitespace })
                for end in 1...max(1, words.count) where end <= words.count {
                    let candidate = words.prefix(end).joined(separator: " ")
                    if initialsMatch(candidate, word: word) { expansion = candidate; break }
                }
            }
            if let expansion { definitions.append((expansion, direct, true)); continue }
            let unquotedBefore = before.trimmingCharacters(in: CharacterSet.whitespacesAndNewlines.union(CharacterSet(charactersIn: "\"'“‘")))
            let unquotedAfter = after.trimmingCharacters(in: CharacterSet(charactersIn: "\"'”’ "))
            if matches("(?:^|[.!?]\\s*)(?:here,?\\s+)?we use(?: the (?:word|term|name))?$", in: unquotedBefore),
               let lead = unquotedAfter.range(of: "^to (?:mean|denote)\\s+", options: [.regularExpression, .caseInsensitive]) {
                let value = String(unquotedAfter[lead.upperBound...]).components(separatedByRegex: "[.!?]")[0].trimmingCharacters(in: .whitespaces)
                if !value.isEmpty { definitions.append((value, direct, false)) }
            }
        }
        if let direct = definitions.first(where: { $0.1 }) { return direct }
        let unique = Set(definitions.map { $0.0.lowercased() })
        return unique.count == 1 ? definitions.first : nil
    }

    private static func matches(_ pattern: String, in text: String) -> Bool {
        text.range(of: pattern, options: [.regularExpression, .caseInsensitive]) != nil
    }
}

private extension String {
    func components(separatedByRegex pattern: String) -> [String] {
        guard let regex = try? NSRegularExpression(pattern: pattern, options: .caseInsensitive) else { return [self] }
        return regex.stringByReplacingMatches(in: self, range: NSRange(startIndex..., in: self), withTemplate: "\u{1f}")
            .components(separatedBy: "\u{1f}")
    }
}
