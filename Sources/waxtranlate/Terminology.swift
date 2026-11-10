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
        let word = canonicalWord(word)
        return glossary.names[word.lowercased()] != nil || ["mvp", "prd", "codex"].contains(word.lowercased()) ||
            (word == word.uppercased() && glossary.acronyms[word] != nil)
    }

    static func lookup(_ passage: Passage) -> TermMeaning? {
        if let selected = passage.selection, let range = Range(selected, in: passage.context), passage.context[range] == passage.text {
            let context = passage.context
            if passage.text == "INTEGER", context.range(of: #"字段|数据类型|整数|编程|数据库|\b(?:column|type|SQL)\b"#, options: [.regularExpression, .caseInsensitive]) != nil {
                return TermMeaning(label: "术语参考", meaning: "整数类型，用于存储没有小数部分的数值。", kind: "数据类型")
            }
            if passage.text == "README" || passage.text == "README.md" {
                return TermMeaning(label: "惯用名称参考", meaning: "项目说明文件，通常介绍项目、安装和使用方法。", kind: "文件名称")
            }
            if passage.text == "VoiceOver", context.range(of: "Apple|苹果|macOS|iOS|辅助功能|读屏|屏幕朗读", options: [.regularExpression, .caseInsensitive]) != nil {
                return TermMeaning(label: "名称参考", meaning: "Apple 的屏幕朗读辅助功能。", kind: "功能名称")
            }
            if passage.text == "Redis", context.range(of: "缓存|数据库|内存|部署|cache|database|deploy", options: [.regularExpression, .caseInsensitive]) != nil {
                return TermMeaning(label: "名称参考", meaning: "一种内存数据存储系统，常用于缓存。", kind: "技术名称")
            }
            if passage.text.lowercased() == "transformer" {
                if context.range(of: "变电|电压|电力|电路|power|voltage", options: [.regularExpression, .caseInsensitive]) != nil {
                    return TermMeaning(label: "语境术语参考", meaning: "变压器，用于改变交流电压。", kind: "技术词")
                }
                if context.range(of: "模型|神经网络|注意力|OCR|attention|neural", options: [.regularExpression, .caseInsensitive]) != nil {
                    return TermMeaning(label: "语境术语参考", meaning: "基于注意力机制的神经网络架构。", kind: "模型架构")
                }
            }
            if passage.text.lowercased() == "token", let hit = passage.selection, let selected = Range(hit, in: context) {
                let before = String(context[..<selected.lowerBound].suffix(18))
                if before.range(of: "(?:数据库|验证|认证|身份|访问|access|auth)[^与，。；]*$", options: [.regularExpression, .caseInsensitive]) != nil {
                    return TermMeaning(label: "语境术语参考", meaning: "令牌，用于表示身份、权限或访问凭据。", kind: "技术词")
                }
                if before.range(of: "(?:模型|输入|分词|文本|language model)[^与，。；]*$", options: [.regularExpression, .caseInsensitive]) != nil {
                    return TermMeaning(label: "语境术语参考", meaning: "词元，模型处理文本时使用的基本单位。", kind: "技术词")
                }
            }
            if passage.text.lowercased() == "attention mask" {
                return TermMeaning(label: "术语参考", meaning: "注意力掩码，用来控制模型可以关注哪些位置。", kind: "英语术语")
            }
            if passage.text.lowercased() == "padding token" {
                return TermMeaning(label: "术语参考", meaning: "填充词元，用于将不同长度的输入补齐。", kind: "英语术语")
            }
        }
        guard !passage.isPhrase, let selection = passage.selection,
              let selected = Range(selection, in: passage.context), passage.context[selected] == passage.text,
              passage.text.count <= 100, let glossary else { return nil }
        let word = canonicalWord(passage.text)
        guard word.range(of: #"^[A-Za-z0-9.+#'’\-]+$"#, options: .regularExpression) != nil else { return nil }
        let key = word.lowercased()
        let clause = TranslationOutput.normalize(localClause(passage))
        let english = passage.sourceLanguage == "en"
        let technicalChinese = matches("代码|编程|接口|程序|服务器|模型|算法|软件|开发|数据库|识别|图片|内存|操作系统|界面|加密", in: clause)
        var acronym = glossary.acronyms[word.uppercased()]
        if word != word.uppercased() {
            if let cue = glossary.lowercaseCues[key] {
                if !matches(cue, in: clause), !matches(chineseLowercaseCues[key] ?? "(?!)", in: clause) { acronym = nil }
            } else if !english && !technicalChinese { acronym = nil }
        } else if ["os", "ai", "ui"].contains(key), !english, !matches("[\\p{Han}]", in: clause) {
            // These short strings are ordinary words in several Latin languages.
            acronym = nil
        }
        let senses = glossary.senses[key] ?? []
        let matching = senses.filter { $0.count == 3 &&
            (matches("(?<![A-Za-z0-9_])(?:" + $0[2] + ")(?![A-Za-z0-9_])", in: clause) ||
             matches(chineseSenseCues[$0[0]] ?? "(?!)", in: clause)) }
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
        if let item = glossary.contextNames[key], item.count == 3,
           matches("(?<![A-Za-z0-9_])(?:" + item[0] + ")(?![A-Za-z0-9_])", in: clause) ||
           matches(chineseNameCues[key] ?? "(?!)", in: clause) {
            return TermMeaning(label: "术语参考", meaning: item[2], kind: item[1])
        }
        let nameKey = matches("^ciallo{2,6}$", in: key) ? "ciallo" : key
        if let item = glossary.names[nameKey], item.count == 2 { return TermMeaning(label: "术语参考", meaning: item[1], kind: item[0]) }
        return nil
    }

    private static func canonicalWord(_ text: String) -> String {
        var word = text.precomposedStringWithCompatibilityMapping
            .replacingOccurrences(of: "['’]s$", with: "", options: [.regularExpression, .caseInsensitive])
        if word.range(of: "^[A-Z]{2,10}s$", options: .regularExpression) != nil { word.removeLast() }
        return word
    }

    private static let chineseLowercaseCues = [
        "ram": "内存|记忆体|DDR[345]", "rag": "检索增强|向量数据库|大语言模型|大模型",
        "ide": "编辑器|调试器|集成开发|代码补全", "rest": "接口|端点|网络服务"
    ]
    // Key by the glossary's expansion, not its array position, so exported data
    // can add or reorder senses without changing these language cues.
    private static let chineseSenseCues = [
        "minimum viable product": "产品|原型|用户|客户|上线|迭代|最小可行",
        "most valuable player": "球员|球赛|球队|赛季|篮球|足球|冠军|联赛|运动员",
        "model-view-presenter": "表示器|呈现器|视图|设计模式|MVP架构",
        "mitral valve prolapse": "二尖瓣|心脏|瓣膜",
        "product requirements document": "产品|需求|文档|功能|评审",
        "Pearl River Delta": "珠三角|珠江|广东|广州|深圳|香港",
        "OpenAI Codex": "编程|代码|代码库|仓库|软件|调试|开发|修复|提交|测试",
        "codex": "手抄本|手稿|古籍|羊皮纸|中世纪|古代书籍",
        "Codex Alimentarius": "食品|食物安全|食品法典"
    ]
    private static let chineseNameCues = [
        "rust": "rust.{0,12}(?:编程|语言|编译器|代码|借用|所有权)|(?:用|使用|采用)\\s*rust.{0,8}(?:开发|编写|实现)|借用检查器",
        "go": "go\\s*(?:语言|编译器|协程|模块)|(?:用|使用)\\s*go.{0,8}(?:开发|编写)|golang",
        "react": "react.{0,12}(?:组件|前端|界面|框架|钩子)|(?:前端|组件|界面).{0,12}react",
        "docker": "docker.{0,12}(?:容器|镜像|部署)|(?:容器|镜像).{0,12}docker",
        "signal": "signal.{0,12}(?:通信|通讯|聊天|加密消息)|(?:使用|安装)\\s*signal.{0,12}(?:消息|通信|通讯|聊天)"
    ]

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
        let pattern = "[,;!?，；。！？]|\\b(?:whereas|while|but)\\b|(?<![A-Za-z0-9_])" +
            NSRegularExpression.escapedPattern(for: passage.text) + "(?![A-Za-z0-9_])"
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
        let evidence = passage.semanticEvidence
        let text = evidence.text
        let selected = evidence.selection
        let pattern = "(?<![A-Za-z0-9_])" + NSRegularExpression.escapedPattern(for: passage.text) + "(?![A-Za-z0-9_])"
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

// Query identity and card presentation are independent of the sentence's language.
struct LookupPolicy {
    enum Object { case word, term, uncertainName, code, region }
    let object: Object
    let term: TermMeaning?
    let passage: Passage

    init(_ passage: Passage) {
        self.passage = passage
        term = LocalTerminology.lookup(passage)
        if passage.context.isEmpty { object = .region }
        else if term != nil { object = .term }
        else if passage.text == "VoiceOver" { object = .uncertainName }
        else if passage.structure == .path || passage.text.range(of: #"[a-z][A-Z]|[_/#]|\.\w+$"#, options: .regularExpression) != nil { object = .code }
        else { object = .word }
    }
    var isChineseContext: Bool { passage.sourceLanguage.hasPrefix("zh") }
    var needsConfirmation: Bool { object == .uncertainName || object == .code }
    var defaultsToContext: Bool {
        if automaticallyTranslatesContext && passage.context != passage.text { return true }
        if object == .word || needsConfirmation { return true }
        guard object == .term, isChineseContext, !["README", "VoiceOver"].contains(passage.text) else { return false }
        let regex = try! NSRegularExpression(pattern: "[A-Za-z][A-Za-z0-9+#]*")
        return regex.numberOfMatches(in: passage.context, range: NSRange(passage.context.startIndex..., in: passage.context)) > 1
    }
    var automaticallyTranslatesContext: Bool {
        if object == .region { return true }
        guard !isChineseContext, passage.structure == .sentence || passage.structure == .list else { return false }
        // The surrounding language controls bilingual context, not whether the
        // selected object was found in the terminology or ordinary dictionary.
        return object == .word || (object == .term && passage.context != passage.text)
    }
    var headwordLanguage: String { passage.headwordLanguage }
    var caption: String {
        if passage.structure == .title { return "标题翻译" }
        if object == .region { return "选区翻译" }
        if passage.structure == .fragment { return "词义参考 · 识别片段" }
        if object == .uncertainName { return "名称待确认" + (isChineseContext ? " · 中文语境" : "") }
        if object == .code { return "代码名称" + (isChineseContext ? " · 中文语境" : "") }
        return (term?.kind ?? (headwordLanguage == "en" ? "英语" : "词语")) + (isChineseContext ? " · 中文语境" : "")
    }
    var unresolvedMessage: String {
        passage.structure == .fragment ? "原文片段不完整，暂不能确认句中含义。" : object == .uncertainName ? "可能指 Apple 的屏幕朗读功能，当前片段不足以确认。" : object == .code ? "暂未确认这个代码名称的含义。" : "本机资料中没有找到可靠解释。"
    }
}
