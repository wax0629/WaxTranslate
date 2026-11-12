import SwiftUI
import NaturalLanguage

enum ReadingLanguage: String, CaseIterable, Identifiable {
    case auto = "", english = "en", japanese = "ja", korean = "ko", french = "fr", german = "de"
    case spanish = "es", italian = "it", portuguese = "pt", russian = "ru", chinese = "zh-Hans"
    var id: String { rawValue }
    var title: String {
        switch self {
        case .auto: return "自动识别"
        case .english: return "英语"
        case .japanese: return "日语"
        case .korean: return "韩语"
        case .french: return "法语"
        case .german: return "德语"
        case .spanish: return "西班牙语"
        case .italian: return "意大利语"
        case .portuguese: return "葡萄牙语"
        case .russian: return "俄语"
        case .chinese: return "中文"
        }
    }
}

enum CaptureShortcut: String, CaseIterable, Identifiable {
    case option, optionShift, controlOption, disabled
    var id: String { rawValue }
    var title: String {
        switch self {
        case .option: return "Option（轻按并松开）"
        case .optionShift: return "Option + Shift + T / R"
        case .controlOption: return "Control + Option + T / R"
        case .disabled: return "仅应用内查词"
        }
    }
    var hoverLabel: String { self == .option ? "Option" : self == .controlOption ? "⌃⌥T" : "⌥⇧T" }
    var regionLabel: String { self == .controlOption ? "⌃⌥R" : "⌥⇧R" }
    var help: String {
        switch self {
        case .option: return "轻按并松开 Option 查词；组合键、拖动或长按不会触发。⌥⇧R 框选，也可从菜单选择「框选翻译」。"
        case .optionShift, .controlOption: return "T 取词，R 框选。也可从菜单选择「框选翻译」。"
        case .disabled: return "在对照翻译中双击原文查词，或从菜单选择「框选翻译」。"
        }
    }
}

@MainActor final class Preferences: ObservableObject {
    private let defaults: UserDefaults
    @Published var language: ReadingLanguage { didSet { defaults.set(language.rawValue, forKey: "reading.sourceLanguage") } }
    @Published var shortcut: CaptureShortcut { didSet { defaults.set(shortcut.rawValue, forKey: "capture.shortcut") } }
    @Published var showOnLaunch: Bool { didSet { defaults.set(showOnLaunch, forKey: "window.showOnLaunch") } }
    @Published var showInDock: Bool { didSet { defaults.set(showInDock, forKey: "window.showInDock") } }

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        language = ReadingLanguage(rawValue: defaults.string(forKey: "reading.sourceLanguage") ?? "") ?? .auto
        shortcut = CaptureShortcut(rawValue: defaults.string(forKey: "capture.shortcut") ?? "") ?? .option
        showOnLaunch = defaults.bool(forKey: "window.showOnLaunch")
        showInDock = defaults.bool(forKey: "window.showInDock")
    }
}

enum LanguageResolver {
    static func resolve(_ text: String, englishDictionaryEvidence: Bool? = nil, headword: NSRange? = nil) -> String {
        let recognizer = NLLanguageRecognizer()
        var sample = text
        // In a short instruction such as “按 Option 键。”, the embedded name
        // can outweigh the surrounding language. Identify that language from its own words.
        if let headword, headword.length < text.utf16.count, text.utf8.contains(where: { $0 >= 128 }),
           let range = Range(headword, in: text), text[range].first.map({ $0.isASCII && $0.isLetter }) == true,
           text[range].allSatisfy(\.isASCII) {
            let word = NSRegularExpression.escapedPattern(for: String(text[range]))
            let surrounding = text.replacingOccurrences(of: "(?<![A-Za-z0-9_])" + word + "(?![A-Za-z0-9_])",
                                                        with: " ", options: .regularExpression)
            if surrounding.range(of: #"\p{Latin}"#, options: .regularExpression) == nil,
               surrounding.range(of: #"[\p{Han}\p{Hiragana}\p{Katakana}\p{Hangul}]"#, options: .regularExpression) != nil {
                sample = surrounding
            }
        }
        recognizer.processString(sample)
        let detected = recognizer.dominantLanguage?.rawValue ?? "en"
        // A single Latin word has little language evidence. Prefer dictionary
        // evidence for isolated words; real sentences keep their language.
        let word = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if LocalTerminology.hasUnambiguousSpelling(word) { return "en" }
        if word.range(of: #"^[A-Za-z]+(?:['’-][A-Za-z]+)*[.!?]?$"#, options: .regularExpression) != nil {
            let probe = Passage(text: word.trimmingCharacters(in: .punctuationCharacters), context: word)
            let knownEnglish = englishDictionaryEvidence ?? !CompactGloss.candidates(for: probe, language: "en").isEmpty
            if knownEnglish { return "en" }
            // Fresh Macs and CI may have no bilingual dictionary. Recheck an
            // isolated word against the app's common Latin reading languages;
            // only replace an out-of-set guess when English wins this check.
            // Full sentences and strong non-English alternatives stay intact.
            let readingLanguages: [NLLanguage] = [.english, .french, .german, .spanish, .italian, .portuguese]
            if !readingLanguages.contains(NLLanguage(rawValue: detected)) {
                let shortlist = NLLanguageRecognizer()
                shortlist.languageConstraints = readingLanguages
                shortlist.processString(word)
                if shortlist.dominantLanguage == .english { return "en" }
            }
        }
        return detected
    }
}
