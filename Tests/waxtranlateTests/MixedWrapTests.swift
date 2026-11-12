#if !BOUNDARY_BASELINE
import AppKit

@MainActor enum MixedWrapTests {
    private static func require(_ value: Bool, _ message: String) throws {
        guard value else { throw NSError(domain: "MixedWrapTests", code: 1, userInfo: [NSLocalizedDescriptionKey: message]) }
    }

    static func run() async throws {
        try clippedRows()
        try keySenses()
        try await vision()
        print("Passed: mixed-script OCR, clipped wrap, bounded recovery, exact positions and contextual Option key.")
    }

    private static func clippedRows() throws {
        let suffix = "以直接按 Option 使用。"
        let prefix = "上一句。版本已经在后台重启，现在可"
        let bounds = CGRect(x: 0, y: 0, width: 800, height: 200)
        func read(_ word: String, upperRight: CGFloat, lowerLeft: CGFloat) throws -> Passage {
            let lines = [(prefix, CGRect(x: 25, y: 116, width: upperRight - 25, height: 22)),
                         (suffix, CGRect(x: lowerLeft, y: 83, width: 210, height: 22))].map { text, frame in
                TextLine(text: text, frame: frame, hit: text.range(of: word).map { NSRange($0, in: text) })
            }
            return try SentenceContext.passage(in: lines, captureBounds: bounds)
        }
        for edges: (CGFloat, CGFloat) in [(798, 25), (690, 2)] {
            let lower = try read("Option", upperRight: edges.0, lowerLeft: edges.1)
            let upper = try read("版本", upperRight: edges.0, lowerLeft: edges.1)
            let earlier = try read("上一句", upperRight: edges.0, lowerLeft: edges.1)
            try require(lower.context == suffix && lower.extent == .missingStart && lower.needsContextExpansion, "Joined over unseen text before the pointer")
            try require(upper.context == "版本已经在后台重启，现在可" && upper.extent == .missingEnd, "Joined over unseen text after the pointer")
            try require(earlier.context == "上一句。" && earlier.hasCompleteContext, "Clipping leaked into the preceding complete sentence")
        }
        let first = TextLine(text: prefix, frame: CGRect(x: 25, y: 116, width: 680, height: 22), hit: nil)
        let last = TextLine(text: suffix, frame: CGRect(x: 25, y: 83, width: 210, height: 22),
                            hit: (suffix as NSString).range(of: "Option"))
        for (gap, sameParagraph): (CGFloat, Bool) in [(33, true), (45, false)] {
            let next = TextLine(text: "这里开始另一句。", frame: CGRect(x: 25, y: 83 - gap, width: 195, height: 22), hit: nil)
            let passage = try SentenceContext.passage(in: [first, last, next], captureBounds: bounds)
            try require(passage.nearbyContext?.contains(next.text) == sameParagraph, "Paragraph spacing did not delimit nearby evidence")
        }
        let full = try read("Option", upperRight: 690, lowerLeft: 25)
        try require(full.context == "版本已经在后台重启，现在可以直接按 Option 使用。" && full.hasCompleteContext, "Lost a fully visible soft wrap")
    }

    private static func keySenses() throws {
        func query(_ text: String, _ word: String = "Option", last: Bool = false) throws -> Passage {
            try SentenceContext.passage(in: text, selection: (text as NSString).range(of: word, options: last ? .backwards : []))
        }
        let repeated = "先按 Option，然后再查看另一个 Option。"
        for text in ["按 Option 键。", "松开 Option。", repeated] {
            let p = try query(text)
            try require(p.sourceLanguage.hasPrefix("zh") && p.headwordLanguage == "en" && !LookupPolicy(p).automaticallyTranslatesContext,
                        "Wrong routing for Chinese instructions: " + text)
            try require(LocalTerminology.lookup(p)?.kind == "键名", "Missing Option key meaning: " + text)
        }
        for text in ["Press Option to open the menu.", "Hold down the Option key."] {
            let p = try query(text)
            try require(LocalTerminology.lookup(p)?.kind == "键名" && p.sourceLanguage == "en", "English keyboard instruction: " + text)
        }
        for (text, word) in [("Choose the best option.", "option"), ("Press Option A to continue.", "Option"),
                             ("请按 Option 按钮继续。", "Option"), (repeated, "Option")] {
            let p = try query(text, word, last: true)
            try require(LocalTerminology.lookup(p) == nil, "Ordinary choice was labeled a key: " + text)
            if text == repeated { try require(p.anchor == (text as NSString).range(of: word, options: .backwards), "Selected wrong Option occurrence") }
        }
        let japanese = try query("Option を押してください。")
        try require(japanese.sourceLanguage == "ja", "Japanese instruction was routed to Chinese")
    }

    private static func vision() async throws {
        let font = NSFont.systemFont(ofSize: 22)
        let style: [NSAttributedString.Key: Any] = [.font: font, .foregroundColor: NSColor.black]
        let first = "上一句说明已经结束。这里用固定样文验证混排文字的换行和截取。新版也已在后台更新并重启，现在可"
        let last = "以直接按 Option 使用。", expected = "新版也已在后台更新并重启，现在可" + last
        let screen = CGRect(x: 0, y: 0, width: 1400, height: 520)
        let image = NSImage(size: screen.size)
        image.lockFocus()
        NSColor.white.setFill(); screen.fill()
        (first as NSString).draw(at: CGPoint(x: 60, y: 277), withAttributes: style)
        (last as NSString).draw(at: CGPoint(x: 60, y: 240), withAttributes: style)
        ("场景" as NSString).draw(at: CGPoint(x: 60, y: 144), withAttributes: style)
        ("另一栏" as NSString).draw(at: CGPoint(x: 820, y: 144), withAttributes: style)
        image.unlockFocus()
        guard let bitmap = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else { throw CocoaError(.fileReadUnknown) }
        func crop(_ area: CGRect) throws -> CGImage {
            let rect = Reader.sourceRect(area, on: screen).applying(CGAffineTransform(scaleX: CGFloat(bitmap.width) / screen.width,
                                                                                       y: CGFloat(bitmap.height) / screen.height))
            guard let slice = bitmap.cropping(to: rect.integral) else { throw CocoaError(.fileReadUnknown) }
            return slice
        }
        func point(_ word: String) -> CGPoint {
            let hit = (last as NSString).range(of: word)
            let before = (last as NSString).substring(to: hit.location) as NSString
            return CGPoint(x: 60 + before.size(withAttributes: style).width + (word as NSString).size(withAttributes: style).width / 2,
                           y: 240 + font.ascender * 0.55)
        }
        // Vision may omit a typographic space at either Han/Latin seam. Keep all
        // source characters and verify the exact UTF-16 hit in the returned text.
        func comparable(_ text: String) -> String {
            text.replacingOccurrences(of: "按 Option", with: "按Option").replacingOccurrences(of: "Option 使用", with: "Option使用")
        }
        let target = point("Option"), small = Reader.hoverRect(at: target, on: screen)
        let firstPass = try Reader.recognize(image: crop(small), target: CGPoint(x: (target.x - small.minX) / small.width,
                                                                                 y: (target.y - small.minY) / small.height), isCrop: true)
        try require(comparable(firstPass.context) == comparable(last) && firstPass.extent == .missingStart, "Small crop treated disconnected rows as a sentence: " + firstPass.context)
        let cache = Reader.HoverCache()
        var requests: [CGRect] = []
        let result = try await cache.passage(at: target, on: screen, displayID: 1, language: nil, trace: LookupTrace()) { area in
            requests.append(area)
            return try crop(area)
        }
        try require(requests == [small, Reader.expandedHoverRect(at: target, on: screen)], "Expected one bounded expansion: " + String(describing: requests))
        try require(result.text == "Option" && comparable(result.context) == comparable(expected) && result.hasCompleteContext &&
                    result.anchor == (result.context as NSString).range(of: "Option") && LocalTerminology.lookup(result)?.kind == "键名",
                    "Unexpected expanded selection: " + result.context)
        let narrow = CGRect(origin: screen.origin, size: CGSize(width: small.width, height: screen.height))
        let clipped = try await cache.passage(at: target, on: narrow, displayID: 2, language: nil, trace: LookupTrace(), image: crop)
        try require(comparable(clipped.context) == comparable(last) && clipped.extent == .missingStart &&
                    !LookupPolicy(clipped).automaticallyTranslatesContext && LocalTerminology.lookup(clipped)?.kind == "键名",
                    "Unrecoverable clipped wrap was presented as complete: " + clipped.context)
        for word in ["直接", "按"] {
            let target = point(word)
            let hit = try await cache.passage(at: target, on: screen, displayID: 1, language: nil, trace: LookupTrace(), image: crop)
            try require(hit.text == word && comparable(hit.context) == comparable(expected) &&
                        hit.anchor == (hit.context as NSString).range(of: word), "Lost a printed Han word: " + hit.text + " / " + hit.context)
        }
    }
}
#endif
