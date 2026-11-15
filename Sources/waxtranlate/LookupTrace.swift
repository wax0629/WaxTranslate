import Foundation

// Opt-in local diagnostics: stage names and durations only, never OCR text,
// translations, screenshots or network payloads.
final class LookupTrace: @unchecked Sendable {
    struct Event: Codable {
        let stage: String
        let durationMs: Double
        let elapsedMs: Double
    }
    private let started = ProcessInfo.processInfo.systemUptime
    private let id = UUID().uuidString.prefix(8)
    private let enabled: Bool
    private let capture: Bool
    private let lock = NSLock()
    private var events: [Event] = []
    init(enabled: Bool = ProcessInfo.processInfo.arguments.contains("--trace-lookup"), capture: Bool = false) {
        self.enabled = enabled
        self.capture = capture
    }
    var snapshot: [Event] { lock.lock(); defer { lock.unlock() }; return events }
    static var now: TimeInterval { ProcessInfo.processInfo.systemUptime }
    func record(_ stage: String, since: TimeInterval) {
        guard enabled || capture else { return }
        let now = Self.now
        if capture {
            lock.lock()
            events.append(Event(stage: stage, durationMs: (now - since) * 1000, elapsedMs: (now - started) * 1000))
            lock.unlock()
        }
        guard enabled else { return }
        let line = String(format: "[lookup %@] %@ %.1f ms; elapsed %.1f ms\n", String(id), stage,
                          (now - since) * 1000, (now - started) * 1000)
        FileHandle.standardError.write(Data(line.utf8))
    }
}

enum TranslationOutput {
    static func normalize(_ text: String, target: String = "zh-Hans") -> String {
        guard target.hasPrefix("zh"), !target.lowercased().contains("hant") else { return text }
        return text.applyingTransform(StringTransform("Traditional-Simplified"), reverse: false) ?? text
    }
}
