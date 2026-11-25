import Foundation
import Darwin

/// The distribution bundle carries both model directions and one universal native library.
struct BundledTranslation: Sendable {
    private typealias Translate = @convention(c) (UnsafePointer<CChar>, UnsafePointer<CChar>, Int32, Int32,
        UnsafeMutablePointer<Int32>, UnsafeMutablePointer<Int32>) -> UnsafeMutablePointer<CChar>?
    private static let translate: Translate? = {
        guard let url = Bundle.main.privateFrameworksURL?.appendingPathComponent("libWaxTranslation.dylib"),
              let library = dlopen(url.path, RTLD_NOW | RTLD_LOCAL),
              let symbol = dlsym(library, "wax_translate") else { return nil }
        return unsafeBitCast(symbol, to: Translate.self)
    }()
    let directory: URL

    init?(source: String) {
        let lang = Locale.Language(identifier: source).languageCode?.identifier
        guard lang == "en" || lang == "zh", let root = Bundle.main.resourceURL else { return nil }
        let model = root.appendingPathComponent("OfflineModels/" + (lang == "en" ? "en-zh" : "zh-en"))
        guard FileManager.default.fileExists(atPath: model.path) else { return nil }
        directory = model
    }

    private func run(_ text: String, selection: Range<Int>? = nil) async throws -> LookupTranslation.Response {
        try Task.checkCancellation()
        // Translation calls use the cooperative executor, outside SwiftUI's main actor.
        guard let translate = Self.translate, !text.utf8.contains(0) else { throw CocoaError(.fileReadCorruptFile) }
        var start: Int32 = -1, end: Int32 = -1
        let output = directory.path.withCString { directory in
            text.withCString { translate(directory, $0, Int32(selection?.lowerBound ?? -1),
                                         Int32(selection?.upperBound ?? -1), &start, &end) }
        }
        guard let output else { throw CocoaError(.fileReadCorruptFile) }
        defer { free(output) }
        try Task.checkCancellation()
        let raw = String(cString: output)
        // This OPUS model can emit a literal SentencePiece space marker in its decoded output.
        // Apply the same cleanup to the two sides of a marked occurrence.
        func clean(_ text: Substring) -> String { text.replacingOccurrences(of: "▁", with: " ") }
        let translated = clean(raw[...])
        var marked = AttributedString(translated)
        if start >= 0, end > start, end <= raw.utf8.count {
            let bytes = raw.utf8
            let from = bytes.index(bytes.startIndex, offsetBy: Int(start))
            let to = bytes.index(bytes.startIndex, offsetBy: Int(end))
            if let lo = String.Index(from, within: raw), let hi = String.Index(to, within: raw) {
                let range = NSRange(location: clean(raw[..<lo]).utf16.count, length: clean(raw[lo..<hi]).utf16.count)
                if let mark = Range(range, in: marked) { marked[mark].inlinePresentationIntent = .stronglyEmphasized }
            }
        }
        return .init(text: translated.trimmingCharacters(in: .whitespacesAndNewlines), attributed: marked)
    }

    func plain(_ input: String) async throws -> String {
        var paragraphs: [String] = []
        for line in input.components(separatedBy: .newlines) {
            if line.trimmingCharacters(in: .whitespaces).isEmpty { paragraphs.append(line); continue }
            paragraphs.append(try await run(line).text)
        }
        return paragraphs.joined(separator: "\n")
    }

    var provider: LookupTranslation.Provider {
        .init(plain: plain, marked: { input in
            let source = String(input.characters)
            var offset = 0
            var selection: Range<Int>?
            for run in input.runs {
                let length = String(input[run.range].characters).utf8.count
                if run.inlinePresentationIntent?.contains(.stronglyEmphasized) == true {
                    selection = (selection?.lowerBound ?? offset)..<(offset + length)
                }
                offset += length
            }
            return try await self.run(source, selection: selection)
        })
    }
}
