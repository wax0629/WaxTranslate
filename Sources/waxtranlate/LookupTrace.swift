import Foundation

// Opt-in local diagnostics: stage names and durations only, never OCR text,
// translations, screenshots or network payloads.
final class LookupTrace: @unchecked Sendable {
    private let started = ProcessInfo.processInfo.systemUptime
    private let id = UUID().uuidString.prefix(8)
    private let enabled: Bool
    init(enabled: Bool = ProcessInfo.processInfo.arguments.contains("--trace-lookup")) { self.enabled = enabled }
    static var now: TimeInterval { ProcessInfo.processInfo.systemUptime }
    func record(_ stage: String, since: TimeInterval) {
        guard enabled else { return }
        let now = Self.now
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
