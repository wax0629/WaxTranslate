import AppKit
import NaturalLanguage
import ScreenCaptureKit
import Vision
import CoreText

struct Passage: Equatable {
    let text: String
    let context: String

    let selection: NSRange?   // Headword in context, in UTF-16.
    let anchor: NSRange?      // Token under the pointer, in the same context.
    let language: String?
    let nearbyContext: String?
    let nearbySelection: NSRange?
    enum Structure: String, Codable { case sentence, list, title, path, fragment }
    let structure: Structure
    var isPhrase: Bool { selection != anchor }

    init(text: String, context: String, selection: NSRange? = nil, anchor: NSRange? = nil, language: String? = nil,
         nearbyContext: String? = nil, nearbySelection: NSRange? = nil, structure: Structure = .sentence) {
        self.structure = structure
        self.text = text
        self.context = context
        // OCR supplies the exact occurrence. Demo/manual passages can infer it.
        self.selection = selection ?? context.range(of: text).map { NSRange($0, in: context) }
        self.anchor = anchor ?? self.selection
        self.language = language?.isEmpty == false ? language : nil
        self.nearbyContext = nearbyContext
        self.nearbySelection = nearbySelection
    }

    var sourceLanguage: String {
        language ?? LanguageResolver.resolve(context.isEmpty ? text : context)
    }

    var headwordLanguage: String { LocalTerminology.lookup(self) == nil ? sourceLanguage : "en" }

    func using(language: String?) -> Passage {
        Passage(text: text, context: context, selection: selection, anchor: anchor, language: language,
                nearbyContext: nearbyContext, nearbySelection: nearbySelection, structure: structure)
    }
}

enum ReaderError: LocalizedError {
    case permission, noText, noScreen
    var errorDescription: String? {
        switch self {
        case .permission: return "请在系统设置的「屏幕与系统音频录制」中允许「我靠翻译」，然后重新打开应用。"
        case .noText: return "这里没有识别到文字。试着将光标移到词的中央，或从菜单使用框选翻译。"
        case .noScreen: return "没有找到光标所在的显示器。"
        }
    }
}

enum Reader {
    // SCStreamConfiguration samples points relative to the selected display's
    // top-left corner; AppKit pointer coordinates use the global bottom-left.
    static func sourceRect(_ rect: CGRect, on screen: CGRect) -> CGRect {
        CGRect(x: rect.minX - screen.minX, y: screen.maxY - rect.maxY, width: rect.width, height: rect.height)
    }

    static func screenshotConfiguration(bounds: CGRect, screen: CGRect, scale: CGFloat) -> SCStreamConfiguration {
        let configuration = SCStreamConfiguration()
        configuration.sourceRect = sourceRect(bounds, on: screen)
        configuration.width = max(1, Int((bounds.width * scale).rounded()))
        configuration.height = max(1, Int((bounds.height * scale).rounded()))
        configuration.showsCursor = false
        return configuration
    }

    static func hoverRect(at point: CGPoint, on screen: CGRect) -> CGRect {
        let height = min(screen.height / 4, 180)
        let width = min(screen.width, 900)
        let bottom = min(max(point.y - height / 2, screen.minY), screen.maxY - height)
        let left = min(max(point.x - width / 2, screen.minX), screen.maxX - width)
        return CGRect(x: left, y: bottom, width: width, height: height)
    }

    @MainActor static func capture(point: CGPoint, region: CGRect?, language: String? = nil, trace: LookupTrace = LookupTrace()) async throws -> Passage {
        guard CGPreflightScreenCaptureAccess() else {
            throw ReaderError.permission
        }
        guard let screen = NSScreen.screens.first(where: { $0.frame.contains(point) }),
              let displayID = screen.deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? CGDirectDisplayID else {
            throw ReaderError.noScreen
        }
        let bounds = region?.intersection(screen.frame) ?? hoverRect(at: point, on: screen.frame)
        let enumerateBegan = LookupTrace.now
        let available = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
        trace.record("capture.enumerate", since: enumerateBegan)
        guard let display = available.displays.first(where: { $0.displayID == displayID }) else { throw ReaderError.noScreen }
        let filter = SCContentFilter(display: display, excludingWindows: [])
        let configuration = screenshotConfiguration(bounds: bounds, screen: screen.frame, scale: screen.backingScaleFactor)
        let captureBegan = LookupTrace.now
        let image = try await SCScreenshotManager.captureImage(contentFilter: filter, configuration: configuration)
        trace.record("capture.image", since: captureBegan)
        let target = region == nil ? CGPoint(x: (point.x - bounds.minX) / bounds.width,
                                               y: (point.y - bounds.minY) / bounds.height) : nil
        let ocrBegan = LookupTrace.now
        return try await Task.detached(priority: .userInitiated) {
            defer { trace.record("capture.ocr", since: ocrBegan) }
            return try recognize(image: image, target: target, language: language)
        }.value
    }

    static func recognize(image: CGImage, target: CGPoint?, language: String? = nil) throws -> Passage {
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.automaticallyDetectsLanguage = language == nil || language == ""
        let requested = language.flatMap { $0.isEmpty ? nil : $0 }
        request.recognitionLanguages = requested.map { [$0] } ?? ["en-US", "zh-Hans", "fr-FR", "de-DE", "es-ES", "it-IT", "ja-JP", "ko-KR", "pt-BR", "ru-RU"]
        try VNImageRequestHandler(cgImage: image).perform([request])
        let lines = (request.results ?? []).compactMap { $0.topCandidates(1).first }
        guard let target else {
            let text = lines.map(\.string).joined(separator: "\n")
            guard !text.isEmpty else { throw ReaderError.noText }
            return Passage(text: text, context: "", language: requested)
        }
        let size = CGSize(width: image.width, height: image.height)
        let point = CGPoint(x: target.x * size.width, y: target.y * size.height)
        return try SentenceContext.passage(in: lines.flatMap { fragments(of: $0, imageSize: size, point: point) }, language: requested)
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
            let hit = wordRange(at: point, in: words, text: text).map {
                NSRange(location: $0.lowerBound.utf16Offset(in: text) - fragment.startIndex.utf16Offset(in: text),
                        length: NSRange($0, in: text).length)
            }
            return TextLine(text: String(fragment).trimmingCharacters(in: .whitespacesAndNewlines),
                            frame: words.reduce(CGRect.null) { $0.union($1.frame) }, hit: hit)
        }
    }

    private static func wordRange(at point: CGPoint,
        in words: [(range: Range<String.Index>, frame: CGRect)], text: String) -> Range<String.Index>? {
        let exact = words.filter { $0.frame.contains(point) }
        // Small UI text has tight glyph boxes rather than a full text line.
        // Allow a little vertical leading while keeping the actual word's
        // horizontal span, so nearby whitespace never selects another word.
        let hits = exact.isEmpty ? words.filter {
            $0.frame.insetBy(dx: 0, dy: -$0.frame.height * 0.2).contains(point)
        } : exact
        guard let first = hits.first else { return nil }
        guard hits.count > 1, let last = hits.last else { return first.range }
        // Vision sometimes reports the same entire packed token box for every
        // character range (docs(logistics), warehouse/parcel). Fit glyph advances
        // inside that shared box instead of always accepting the first word.
        var start = first.range.lowerBound
        var end = last.range.upperBound
        while start > text.startIndex {
            let previous = text.index(before: start)
            guard text[previous].isPunctuation else { break }
            start = previous
        }
        while end < text.endIndex, text[end].isPunctuation { end = text.index(after: end) }
        let segment = String(text[start..<end])
        let styled = NSAttributedString(string: segment, attributes: [.font: NSFont.systemFont(ofSize: 100)])
        let line = CTLineCreateWithAttributedString(styled)
        let advance = CTLineGetTypographicBounds(line, nil, nil, nil)
        let frame = hits.reduce(CGRect.null) { $0.union($1.frame) }
        guard advance > 0, frame.width > 0 else { return nil }
        let position = (point.x - frame.minX) / frame.width * advance
        let offset = start.utf16Offset(in: text)
        return hits.first { word in
            let lower = CTLineGetOffsetForStringIndex(line, word.range.lowerBound.utf16Offset(in: text) - offset, nil)
            let upper = CTLineGetOffsetForStringIndex(line, word.range.upperBound.utf16Offset(in: text) - offset, nil)
            return position >= lower && position <= upper
        }?.range
    }
}
