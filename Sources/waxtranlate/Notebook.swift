import SwiftUI

struct Entry: Codable, Identifiable {
    let id: UUID
    let source: String
    let target: String
    let context: String
    let sentenceTranslation: String?
    var due: Date
    var streak: Int

    var displayMeaning: String {
        // v0.1 saved raw bilingual entries, including all their examples.
        if !context.isEmpty && target.contains(" | "), let gloss = CompactGloss.meanings(in: target).first {
            return gloss
        }
        return target
    }
}

@MainActor final class Notebook: ObservableObject {
    @Published private(set) var entries: [Entry]
    private let defaults: UserDefaults
    private let key = "notebook.entries.v1"

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        entries = defaults.data(forKey: key).flatMap { try? JSONDecoder().decode([Entry].self, from: $0) } ?? []
    }

    func contains(_ passage: Passage) -> Bool {
        entries.contains { $0.source == passage.text && $0.context == passage.context }
    }

    func save(_ passage: Passage, translation: String, sentenceTranslation: String? = nil) {
        guard !contains(passage) else { return }
        entries.insert(Entry(id: UUID(), source: passage.text, target: translation, context: passage.context,
                             sentenceTranslation: sentenceTranslation, due: Date(), streak: 0), at: 0)
        persist()
    }

    func remove(_ id: UUID) {
        entries.removeAll { $0.id == id }
        persist()
    }

    func review(_ id: UUID, remembered: Bool, now: Date = Date()) {
        guard let i = entries.firstIndex(where: { $0.id == id }) else { return }
        let days = [1, 3, 7, 14, 30, 60]
        let next = remembered ? min(entries[i].streak + 1, days.count) : 0
        entries[i].streak = next
        entries[i].due = next == 0 ? now.addingTimeInterval(600)
            : Calendar.current.date(byAdding: .day, value: days[next - 1], to: now)!
        persist()
    }

    private func persist() {
        if let data = try? JSONEncoder().encode(entries) { defaults.set(data, forKey: key) }
    }
}
