import AppKit
import NaturalLanguage
import ScreenCaptureKit
import Vision
import CoreText
import CryptoKit

struct Passage: Equatable {
    let text: String
    let context: String

    let selection: NSRange?   // Headword in context, in UTF-16.
    let anchor: NSRange?      // Token under the pointer, in the same context.
    let language: String?
    let nearbyContext: String?
    let nearbySelection: NSRange?
    enum Structure: String, Codable { case sentence, list, title, path, code, fragment }
    let structure: Structure
    let extent: ContextExtent
    var isPhrase: Bool { selection != anchor && text.contains(where: \.isWhitespace) }

    init(text: String, context: String, selection: NSRange? = nil, anchor: NSRange? = nil, language: String? = nil,
         nearbyContext: String? = nil, nearbySelection: NSRange? = nil, structure: Structure = .sentence, extent: ContextExtent = .complete) {
        self.structure = structure
        self.extent = extent
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
        language ?? LanguageResolver.resolve(context.isEmpty ? text : context, headword: selection)
    }

    var headwordLanguage: String {
        let source = sourceLanguage
        let latin = text.range(of: #"^[A-Za-z][A-Za-z0-9 .+#_’'\-]*$"#, options: .regularExpression) != nil
        return source.hasPrefix("zh") && latin ? "en" : source
    }

    // Same block evidence can explain a preceding definition; another paragraph
    // or item cannot. Raw capture remains available in memory for diagnostics.
    var semanticEvidence: (text: String, selection: NSRange?) {
        if let nearbyContext, let nearbySelection,
           let block = try? SentenceContext.evidence(in: nearbyContext, selection: nearbySelection) {
            return (block.text, block.selection)
        }
        return (context, selection)
    }

    func selecting(_ range: NSRange) -> Passage? {
        guard let selected = Range(range, in: context) else { return nil }
        let evidence = semanticEvidence
        let evidenceOffset = (evidence.selection?.location ?? selection?.location ?? 0) - (selection?.location ?? 0)
        return Passage(text: String(context[selected]), context: context, selection: range, language: language,
                       nearbyContext: evidence.text, nearbySelection: NSRange(location: range.location + evidenceOffset, length: range.length), structure: structure, extent: extent)
    }

    var wholeTitle: Passage { Passage(text: context, context: "", language: language, structure: .title) }

    func using(language: String?) -> Passage {
        Passage(text: text, context: context, selection: selection, anchor: anchor, language: language,
                nearbyContext: nearbyContext, nearbySelection: nearbySelection, structure: structure, extent: extent)
    }

    var hasCompleteContext: Bool { extent == .complete && structure != .fragment }
    var needsContextExpansion: Bool {
        !context.isEmpty && !hasCompleteContext && (context != text || extent != .uncertain) && [.sentence, .list, .fragment].contains(structure)
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

    struct Display {
        let id: CGDirectDisplayID
        let frame: CGRect
        let scale: CGFloat

        @MainActor init?(at point: CGPoint) {
            guard let screen = NSScreen.screens.first(where: { $0.frame.contains(point) }),
                  let id = screen.deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? CGDirectDisplayID else { return nil }
            self.id = id
            frame = screen.frame
            scale = screen.backingScaleFactor
        }
    }

    static func capture(point: CGPoint, region: CGRect?, display: Display?, language: String?, readableWindows: Set<CGWindowID>,
                        hoverCache: HoverCache, trace: LookupTrace) async throws -> Passage {
        try Task.checkCancellation()
        guard CGPreflightScreenCaptureAccess() else { throw ReaderError.permission }
        guard let display else { throw ReaderError.noScreen }
        let enumerateBegan = LookupTrace.now
        let pid = ProcessInfo.processInfo.processIdentifier
        var available = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
        // Our first panel may still be laying out during enumeration. If our app
        // is absent, wait for that main-thread update before refreshing its windows.
        if region == nil, !available.applications.contains(where: { $0.processID == pid }),
           await MainActor.run(body: { NSApp.windows.contains { $0 is NSPanel && $0.isVisible } }) {
            try Task.checkCancellation()
            available = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: false)
        }
        trace.record("capture.enumerate", since: enumerateBegan)
        guard let source = available.displays.first(where: { $0.displayID == display.id }) else { throw ReaderError.noScreen }
        // Exclude transient UI even while WindowServer is still compositing a dismissed panel.
        let filter: SCContentFilter
        if let app = available.applications.first(where: { $0.processID == pid }) {
            let visible = available.windows.filter { $0.owningApplication?.processID == pid && readableWindows.contains($0.windowID) }
            filter = SCContentFilter(display: source, excludingApplications: [app], exceptingWindows: visible)
        } else {
            filter = SCContentFilter(display: source, excludingWindows: [])
        }
        func image(in area: CGRect) async throws -> CGImage {
            try Task.checkCancellation()
            let configuration = screenshotConfiguration(bounds: area, screen: display.frame, scale: display.scale)
            let began = LookupTrace.now
            let image = try await SCScreenshotManager.captureImage(contentFilter: filter, configuration: configuration)
            trace.record("capture.image", since: began)
            try Task.checkCancellation()
            return image
        }
        if let region {
            let regionImage = try await image(in: region.intersection(display.frame))
            let began = LookupTrace.now
            defer { trace.record("capture.ocr", since: began) }
            return try await recognizeCancellable(image: regionImage, target: nil, language: language, isCrop: false)
        }
        return try await hoverCache.passage(at: point, on: display.frame, displayID: display.id, language: language, trace: trace, image: image)
    }

    // A neighboring word can use the previous accurate observations only after a new
    // screenshot confirms the pixels. Keep one crop in memory, including its geometry.
    actor HoverCache {
        private struct Entry {
            let area: CGRect
            let displayID: CGDirectDisplayID
            let language: String?
            let size: CGSize
            let digest: SHA256.Digest
            let lines: [VNRecognizedText]
        }
        private var last: Entry?

        func passage(at point: CGPoint, on screen: CGRect, displayID: CGDirectDisplayID, language: String?, trace: LookupTrace,
                     image: (CGRect) async throws -> CGImage) async throws -> Passage {
            try Task.checkCancellation()
            let bounds = Reader.hoverRect(at: point, on: screen)
            let previous = last
            func target(in area: CGRect) -> CGPoint {
                CGPoint(x: (point.x - area.minX) / area.width, y: (point.y - area.minY) / area.height)
            }
            func read(_ area: CGRect) async throws -> Passage {
                let current = try await image(area)
                let began = LookupTrace.now
                let size = CGSize(width: current.width, height: current.height)
                let fingerprint = Self.digest(current)
                try Task.checkCancellation()
                let lines: [VNRecognizedText]
                if let previous, previous.displayID == displayID, previous.area == area, previous.size == size,
                   previous.language == language, previous.digest == fingerprint {
                    lines = previous.lines
                    trace.record("capture.ocr_reused", since: began)
                } else {
                    lines = try await Reader.linesCancellable(in: current, language: language)
                    if let fingerprint {
                        try Task.checkCancellation()
                        last = Entry(area: area, displayID: displayID, language: language, size: size, digest: fingerprint, lines: lines)
                    }
                    trace.record("capture.ocr", since: began)
                }
                return try Reader.passage(in: lines, size: size, target: target(in: area), language: language, isCrop: true)
            }
            // For nearby words, first sample the same area again. Changed pixels run
            // fresh OCR on that screenshot. Recenter on a miss or an incomplete crop.
            if let previous, previous.displayID == displayID, previous.language == language,
               previous.area != bounds, previous.area.size == bounds.size, screen.contains(previous.area),
               previous.area.insetBy(dx: bounds.width / 4, dy: bounds.height / 4).contains(point) {
                do {
                    let nearby = try await read(previous.area)
                    if nearby.hasCompleteContext { return nearby }
                } catch ReaderError.noText { /* Retry with the normal centered crop. */ }
                try Task.checkCancellation()
            }
            let first = try await read(bounds)
            return try await ContextCapture.complete(first) {
                let expanded = Reader.expandedHoverRect(at: point, on: screen)
                guard expanded != bounds else { return first }
                let began = LookupTrace.now
                defer { trace.record("capture.expand", since: began) }
                return try await Reader.recognizeCancellable(image: image(expanded), target: target(in: expanded),
                                                             language: language, isCrop: true)
            }
        }

        // A CGImage can be a slice backed by its parent's provider. Hash the drawn
        // pixels in a fixed color space, independent of provider padding and origin.
        private static func digest(_ image: CGImage) -> SHA256.Digest? {
            let rowBytes = image.width * 4
            guard let space = CGColorSpace(name: CGColorSpace.sRGB),
                  let canvas = CGContext(data: nil, width: image.width, height: image.height, bitsPerComponent: 8,
                                         bytesPerRow: rowBytes, space: space, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue),
                  let bytes = canvas.data else { return nil }
            canvas.setBlendMode(.copy)
            canvas.draw(image, in: CGRect(x: 0, y: 0, width: image.width, height: image.height))
            return SHA256.hash(data: UnsafeRawBufferPointer(start: bytes, count: rowBytes * image.height))
        }
    }

    static func expandedHoverRect(at point: CGPoint, on screen: CGRect) -> CGRect {
        let width = min(screen.width, 1200), height = min(screen.height, 480)
        return CGRect(x: min(max(point.x - width / 2, screen.minX), screen.maxX - width),
                      y: min(max(point.y - height / 2, screen.minY), screen.maxY - height), width: width, height: height)
    }

    // Load the accurate text recognizer once, using a known word without accessing the screen.
    static func warmUp(language: String?) async {
        guard !Task.isCancelled,
              let canvas = CGContext(data: nil, width: 160, height: 48, bitsPerComponent: 8, bytesPerRow: 160,
                                     space: CGColorSpaceCreateDeviceGray(), bitmapInfo: CGImageAlphaInfo.none.rawValue) else { return }
        canvas.setFillColor(gray: 1, alpha: 1)
        canvas.fill(CGRect(x: 0, y: 0, width: canvas.width, height: canvas.height))
        canvas.setFillColor(gray: 0, alpha: 1)
        canvas.textPosition = CGPoint(x: 8, y: 12)
        let word = NSAttributedString(string: "Read", attributes: [.font: CTFontCreateWithName("Helvetica" as CFString, 26, nil)])
        CTLineDraw(CTLineCreateWithAttributedString(word), canvas)
        guard let image = canvas.makeImage() else { return }
        _ = try? await recognizeCancellable(image: image, target: nil, language: language, isCrop: false)
    }

    private static func recognizeCancellable(image: CGImage, target: CGPoint?, language: String?, isCrop: Bool) async throws -> Passage {
        let lines = try await linesCancellable(in: image, language: language)
        return try passage(in: lines, size: CGSize(width: image.width, height: image.height), target: target, language: language, isCrop: isCrop)
    }

    private static func linesCancellable(in image: CGImage, language: String?) async throws -> [VNRecognizedText] {
        let request = VNRecognizeTextRequest()
        return try await withTaskCancellationHandler {
            try Task.checkCancellation()
            let lines = try recognizedLines(in: image, language: language, request: request)
            try Task.checkCancellation()
            return lines
        } onCancel: { request.cancel() }
    }

    static func recognize(image: CGImage, target: CGPoint?, language: String? = nil, isCrop: Bool = false) throws -> Passage {
        let lines = try recognizedLines(in: image, language: language, request: VNRecognizeTextRequest())
        return try passage(in: lines, size: CGSize(width: image.width, height: image.height), target: target, language: language, isCrop: isCrop)
    }

    private static func recognizedLines(in image: CGImage, language: String?, request: VNRecognizeTextRequest) throws -> [VNRecognizedText] {
        request.recognitionLevel = .accurate
        request.automaticallyDetectsLanguage = language == nil || language == ""
        let requested = language.flatMap { $0.isEmpty ? nil : $0 }
        request.recognitionLanguages = requested.map { [$0] } ?? ["en-US", "zh-Hans", "fr-FR", "de-DE", "es-ES", "it-IT", "ja-JP", "ko-KR", "pt-BR", "ru-RU"]
        try VNImageRequestHandler(cgImage: image).perform([request])
        return (request.results ?? []).compactMap { $0.topCandidates(1).first }
    }

    private static func passage(in lines: [VNRecognizedText], size: CGSize, target: CGPoint?, language: String?, isCrop: Bool) throws -> Passage {
        let requested = language.flatMap { $0.isEmpty ? nil : $0 }
        guard let target else {
            let text = lines.map(\.string).joined(separator: "\n")
            guard !text.isEmpty else { throw ReaderError.noText }
            return Passage(text: text, context: "", language: requested)
        }
        let point = CGPoint(x: target.x * size.width, y: target.y * size.height)
        return try SentenceContext.passage(in: lines.flatMap { fragments(of: $0, imageSize: size, point: point) }, language: requested,
                                           captureBounds: isCrop ? CGRect(origin: .zero, size: size) : nil)
    }

    // Vision can group two columns on the same baseline into one observation.
    // Split at large spatial gaps, keeping punctuation between ordinary words.
    private static func fragments(of line: VNRecognizedText, imageSize: CGSize, point: CGPoint) -> [TextLine] {
        let text = line.string
        let tokenizer = NLTokenizer(unit: .word)
        tokenizer.string = text
        typealias Word = (range: Range<String.Index>, frame: CGRect)
        var groups: [[Word]] = []
        // Batch tokenization can omit adjacent Han words in mixed-script labels.
        // Ask at each boundary so a printed word cannot look like a column gutter.
        var cursor = text.startIndex
        while cursor < text.endIndex {
            let range = tokenizer.tokenRange(at: cursor)
            guard range.contains(cursor) else { cursor = text.index(after: cursor); continue }
            cursor = range.upperBound
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
