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
    case optionShift, controlOption, disabled
    var id: String { rawValue }
    var title: String {
        switch self {
        case .optionShift: return "Option + Shift + T / R"
        case .controlOption: return "Control + Option + T / R"
        case .disabled: return "仅应用内查词"
        }
    }
    var hoverLabel: String { self == .controlOption ? "⌃⌥T" : "⌥⇧T" }
    var regionLabel: String { self == .controlOption ? "⌃⌥R" : "⌥⇧R" }
}

@MainActor final class Preferences: ObservableObject {
    private let defaults: UserDefaults
    @Published var language: ReadingLanguage { didSet { defaults.set(language.rawValue, forKey: "reading.sourceLanguage") } }
    @Published var shortcut: CaptureShortcut { didSet { defaults.set(shortcut.rawValue, forKey: "capture.shortcut") } }
    @Published var showOnLaunch: Bool { didSet { defaults.set(showOnLaunch, forKey: "window.showOnLaunch") } }
    @Published var onlineReferences: Bool { didSet { defaults.set(onlineReferences, forKey: "lookup.onlineReferences") } }

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        language = ReadingLanguage(rawValue: defaults.string(forKey: "reading.sourceLanguage") ?? "") ?? .auto
        shortcut = CaptureShortcut(rawValue: defaults.string(forKey: "capture.shortcut") ?? "") ?? .optionShift
        showOnLaunch = defaults.bool(forKey: "window.showOnLaunch")
        onlineReferences = defaults.object(forKey: "lookup.onlineReferences") == nil || defaults.bool(forKey: "lookup.onlineReferences")
    }
}

enum LanguageResolver {
    static func resolve(_ text: String, englishDictionaryEvidence: Bool? = nil) -> String {
        let recognizer = NLLanguageRecognizer()
        recognizer.processString(text)
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
