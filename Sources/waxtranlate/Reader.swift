import AppKit
import NaturalLanguage
import ScreenCaptureKit
import Vision

struct Passage: Equatable {
    let text: String
    let context: String

    let selection: NSRange?

    init(text: String, context: String, selection: NSRange? = nil) {
        self.text = text
        self.context = context
        // OCR supplies the exact occurrence. Demo/manual passages can use a unique match.
        self.selection = selection ?? context.range(of: text).map { NSRange($0, in: context) }
    }

    var sourceLanguage: String {
        let recognizer = NLLanguageRecognizer()
        recognizer.processString(context.isEmpty ? text : context)
        return recognizer.dominantLanguage?.rawValue ?? "en"
    }
}

enum ReaderError: LocalizedError {
    case permission, noText, noScreen
    var errorDescription: String? {
        switch self {
        case .permission: return "请在系统设置的「屏幕与系统音频录制」中允许「waxtranlate」，然后重新打开应用。"
        case .noText: return "这里没有识别到文字。试着将光标移到词的中央，或使用区域翻译。"
        case .noScreen: return "没有找到光标所在的显示器。"
        }
    }
}

enum Reader {
    // ScreenCaptureKit uses the primary display's top-left origin.
    static func displayRect(_ rect: CGRect, primaryHeight: CGFloat) -> CGRect {
        CGRect(x: rect.minX, y: primaryHeight - rect.maxY, width: rect.width, height: rect.height)
    }

    static func hoverRect(at point: CGPoint, on screen: CGRect) -> CGRect {
        let height = screen.height / 4
        let bottom = min(max(point.y - height / 2, screen.minY), screen.maxY - height)
        return CGRect(x: screen.minX, y: bottom, width: screen.width, height: height)
    }

    @MainActor static func capture(point: CGPoint, region: CGRect?) async throws -> Passage {
        guard CGPreflightScreenCaptureAccess() else {
            throw ReaderError.permission
        }
        guard let primary = NSScreen.screens.first,
              let screen = NSScreen.screens.first(where: { $0.frame.contains(point) }) else {
            throw ReaderError.noScreen
        }
        let bounds = region?.intersection(screen.frame) ?? hoverRect(at: point, on: screen.frame)
        let image = try await SCScreenshotManager.captureImage(in: displayRect(bounds, primaryHeight: primary.frame.height))
        let target = region == nil ? CGPoint(x: (point.x - bounds.minX) / bounds.width,
                                               y: (point.y - bounds.minY) / bounds.height) : nil
        return try await Task.detached(priority: .userInitiated) {
            try recognize(image: image, target: target)
        }.value
    }

    static func recognize(image: CGImage, target: CGPoint?) throws -> Passage {
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.automaticallyDetectsLanguage = true
        request.recognitionLanguages = ["en-US", "zh-Hans", "fr-FR", "de-DE", "es-ES", "ja-JP", "ko-KR", "pt-BR"]
        try VNImageRequestHandler(cgImage: image).perform([request])
        let lines = (request.results ?? []).compactMap { $0.topCandidates(1).first }
        guard let target else {
            let text = lines.map(\.string).joined(separator: "\n")
            guard !text.isEmpty else { throw ReaderError.noText }
            return Passage(text: text, context: "")
        }
        let size = CGSize(width: image.width, height: image.height)
        let point = CGPoint(x: target.x * size.width, y: target.y * size.height)
        return try SentenceContext.passage(in: lines.flatMap { fragments(of: $0, imageSize: size, point: point) })
    }

    // Vision can group two columns on the same baseline into one observation.
    // Split at large spatial gaps, keeping punctuation between ordinary words.
    private static func fragments(of line: VNRecognizedText, imageSize: CGSize, point: CGPoint) -> [TextLine] {
        let text = line.string
        let tokenizer = NLTokenizer(unit: .word)
        tokenizer.string = text
        typealias Word = (range: Range<String.Index>, frame: CGRect)
        var groups: [[Word]] = []
        for range in tokenizer.tokens(for: text.startIndex..<text.endIndex) {
            guard let box = try? line.boundingBox(for: range) else { continue }
            let rect = box.boundingBox.applying(CGAffineTransform(scaleX: imageSize.width, y: imageSize.height))
            if let previous = groups.last?.last,
               rect.minX - previous.frame.maxX <= 2.2 * max(previous.frame.height, rect.height) {
                groups[groups.count - 1].append((range, rect))
            } else {
                groups.append([(range, rect)])
            }
        }
        return groups.indices.map { i in
            let words = groups[i]
            let start = i == 0 ? text.startIndex : words[0].range.lowerBound
            let end = i + 1 == groups.count ? text.endIndex : groups[i + 1][0].range.lowerBound
            let fragment = text[start..<end].drop(while: { $0.isWhitespace })
            let hit = words.first { $0.frame.contains(point) }.map {
                NSRange(location: $0.range.lowerBound.utf16Offset(in: text) - fragment.startIndex.utf16Offset(in: text),
                        length: NSRange($0.range, in: text).length)
            }
            return TextLine(text: String(fragment).trimmingCharacters(in: .whitespacesAndNewlines),
                            frame: words.reduce(CGRect.null) { $0.union($1.frame) }, hit: hit)
        }
    }
}
