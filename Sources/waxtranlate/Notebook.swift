import SwiftUI

struct Entry: Codable, Identifiable {
    let id: UUID
    let source: String
    let target: String
    let context: String
    let sentenceTranslation: String?
    var due: Date
    var streak: Int
    var language: String? = nil
    var selection: NSRange? = nil
    var anchor: NSRange? = nil

    var displayMeaning: String {
        if !context.isEmpty && target.contains(" | "), let gloss = CompactGloss.meanings(in: target).first { return gloss }
        return TranslationOutput.normalize(target, target: passage.sourceLanguage.hasPrefix("zh") ? "en" : "zh-Hans")
    }
    var displaySentenceTranslation: String? { sentenceTranslation.map { TranslationOutput.normalize($0, target: passage.sourceLanguage.hasPrefix("zh") ? "en" : "zh-Hans") } }
    var passage: Passage { Passage(text: source, context: context, selection: selection, anchor: anchor, language: language) }
}

struct RecentLookup: Codable, Identifiable {
    let id: UUID
    let passage: StoredPassage
    var meaning: String
    let date: Date
    var word: String { passage.text }
    var displayMeaning: String { TranslationOutput.normalize(meaning, target: passage.language.hasPrefix("zh") ? "en" : "zh-Hans") }
}

struct StoredPassage: Codable {
    let text: String
    let context: String
    let selection: NSRange?
    let anchor: NSRange?
    let language: String
    var value: Passage { Passage(text: text, context: context, selection: selection, anchor: anchor, language: language) }
}

private struct LookupActivity: Codable {
    var total = 0
    var day = Date.distantPast
    var today = 0
    var recent: [RecentLookup] = []
}

@MainActor final class Notebook: ObservableObject {
    @Published private(set) var entries: [Entry] = []
    @Published private var activity = LookupActivity()
    @Published private(set) var error: String?
    private let defaults: UserDefaults
    private let key = "notebook.entries.v1"
    private let activityKey = "notebook.activity.v1"
    private var readableEntries = true
    private var readableActivity = true

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        if let data = defaults.data(forKey: key) {
            do { entries = try JSONDecoder().decode([Entry].self, from: data) }
            catch { readableEntries = false; self.error = "生词本暂时无法读取，原数据已保留。请备份后重新打开，或在设置中查看数据位置。" }
        }
        if let data = defaults.data(forKey: activityKey) {
            do { activity = try JSONDecoder().decode(LookupActivity.self, from: data) }
            catch { readableActivity = false; self.error = "学习记录暂时无法读取，原数据已保留。请备份后重新打开。" }
        }
    }

    var totalLookups: Int { activity.total }
    var recent: [RecentLookup] { activity.recent }
    var masteredCount: Int { entries.filter { $0.streak >= 3 }.count }
    func todayLookups(now: Date = Date()) -> Int { Calendar.current.isDate(activity.day, inSameDayAs: now) ? activity.today : 0 }
    func dueCount(now: Date = Date()) -> Int { entries.filter { $0.due <= now }.count }

    func contains(_ passage: Passage) -> Bool { entries.contains { sameEntry($0, passage) } }

    private func sameEntry(_ entry: Entry, _ passage: Passage) -> Bool {
        entry.source == passage.text && entry.context == passage.context &&
        (entry.language == nil || entry.language == passage.sourceLanguage) &&
        (entry.selection == nil || entry.selection == passage.selection)
    }

    @discardableResult func save(_ passage: Passage, translation: String, sentenceTranslation: String? = nil) -> Bool {
        guard !contains(passage), !translation.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return false }
        var next = entries
        let target = passage.sourceLanguage.hasPrefix("zh") ? "en" : "zh-Hans"
        next.insert(Entry(id: UUID(), source: passage.text, target: TranslationOutput.normalize(translation, target: target), context: passage.context,
                          sentenceTranslation: sentenceTranslation.map { TranslationOutput.normalize($0, target: target) }, due: Date(), streak: 0,
                          language: passage.sourceLanguage, selection: passage.selection, anchor: passage.anchor), at: 0)
        return persist(next)
    }

    func remove(_ id: UUID) { _ = persist(entries.filter { $0.id != id }) }

    func review(_ id: UUID, remembered: Bool, now: Date = Date()) {
        guard let i = entries.firstIndex(where: { $0.id == id }) else { return }
        var nextEntries = entries
        let days = [1, 3, 7, 14, 30, 60]
        let next = remembered ? min(nextEntries[i].streak + 1, days.count) : 0
        nextEntries[i].streak = next
        nextEntries[i].due = next == 0 ? now.addingTimeInterval(600)
            : Calendar.current.date(byAdding: .day, value: days[next - 1], to: now) ?? now.addingTimeInterval(86400)
        _ = persist(nextEntries)
    }

    @discardableResult func recordLookup(_ passage: Passage, meaning: String, now: Date = Date()) -> UUID? {
        guard readableActivity, !meaning.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
        var next = activity
        next.total += 1
        next.today = Calendar.current.isDate(next.day, inSameDayAs: now) ? next.today + 1 : 1
        next.day = now
        next.recent.removeAll { $0.word.caseInsensitiveCompare(passage.text) == .orderedSame && $0.passage.language == passage.sourceLanguage }
        let id = UUID()
        next.recent.insert(RecentLookup(id: id,
            passage: StoredPassage(text: passage.text, context: passage.context, selection: passage.selection, anchor: passage.anchor, language: passage.sourceLanguage),
            meaning: String(meaning.prefix(120)), date: now), at: 0)
        next.recent = Array(next.recent.prefix(6))
        guard let data = try? JSONEncoder().encode(next) else { error = "学习记录未能保存，请重试。"; return nil }
        defaults.set(data, forKey: activityKey)
        activity = next
        return id
    }

    func updateLookup(_ id: UUID, meaning: String) {
        guard readableActivity, let index = activity.recent.firstIndex(where: { $0.id == id }) else { return }
        var next = activity
        next.recent[index].meaning = String(meaning.prefix(120))
        guard let data = try? JSONEncoder().encode(next) else { return }
        defaults.set(data, forKey: activityKey)
        activity = next
    }

    @discardableResult private func persist(_ next: [Entry]) -> Bool {
        guard readableEntries else { return false }
        do {
            let data = try JSONEncoder().encode(next)
            defaults.set(data, forKey: key)
            entries = next
            return true
        } catch { self.error = "生词本未能保存，请重试。"; return false }
    }
}
