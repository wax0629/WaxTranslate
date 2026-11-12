import AppKit

// Shared contract cases use explicit hit markers, not platform string offsets.
// The same JSON is consumed by the Windows acceptance suite after Mac passes.
@main @MainActor struct SentenceBoundaryTests {
    struct Corpus: Decodable { let version: Int; let cases: [Sample] }
    struct Line: Decodable { let text: String; var x, y, width, height: Double }
    struct Sample: Decodable {
        let id, category, mode, language, expected, structure, extent: String
        let input: String?
        let lines: [Line]?
        let capture: [Double]?
        let query: String?
        let automatic: Bool
        let reflow: Bool?
    }
    static func marked(_ source: String) -> (String, NSRange?) {
        guard let a = source.range(of: "⟦"), let b = source.range(of: "⟧") else { return (source, nil) }
        let prefix = String(source[..<a.lowerBound]), selected = String(source[a.upperBound..<b.lowerBound])
        return (prefix + selected + source[b.upperBound...], NSRange(location: prefix.utf16.count, length: selected.utf16.count))
    }
    static func main() async {
        do { try await run() }
        catch {
            FileHandle.standardError.write(Data("Boundary acceptance failed: \(error)\n".utf8))
            exit(1)
        }
    }
    static func run() async throws {
        let path = CommandLine.arguments.dropFirst().first ?? "Tests/Fixtures/sentence-boundaries.json"
        let corpus = try JSONDecoder().decode(Corpus.self, from: Data(contentsOf: URL(fileURLWithPath: path)))
        precondition(corpus.version == 1)
        var failures: [String] = [], count = 0
        func check(_ sample: Sample, text: String? = nil, scale: Double = 1, dx: Double = 0, dy: Double = 0, reversed: Bool = false) {
            count += 1
            let name = "\(sample.id) [\(sample.category), reflow=\(text != nil), scale=\(scale), shift=\(dx),\(dy), reverse=\(reversed)]"
            do {
                let passage: Passage
                if sample.mode == "editor" {
                    let source = marked(text ?? sample.input!)
                    passage = try SentenceContext.passage(in: source.0, selection: source.1!, language: sample.language)
                } else {
                    var lines = sample.lines!.map { line -> TextLine in
                        let source = marked(line.text)
                        return TextLine(text: source.0,
                                        frame: CGRect(x: line.x * scale + dx, y: -(line.y + line.height) * scale - dy,
                                                      width: line.width * scale, height: line.height * scale), hit: source.1)
                    }
                    if reversed { lines.reverse() }
                    #if BOUNDARY_BASELINE
                    passage = try SentenceContext.passage(in: lines, language: sample.language)
                    #else
                    let bounds = sample.capture.map { CGRect(x: $0[0] * scale + dx, y: -($0[1] + $0[3]) * scale - dy,
                                                              width: $0[2] * scale, height: $0[3] * scale) }
                    passage = try SentenceContext.passage(in: lines, language: sample.language, captureBounds: bounds)
                    if passage.structure != .title {
                        let analysis = try ContextBoundary.analyze(lines, source: .ocr, captureBounds: bounds)
                        guard analysis.sources.allSatisfy({ $0.range.location >= 0 && NSMaxRange($0.range) <= analysis.context.utf16.count }),
                              analysis.sources.contains(where: { NSIntersectionRange($0.range, analysis.pointerHit).length > 0 }) else {
                            throw NSError(domain: "BoundarySourceMap", code: 1)
                        }
                    }
                    #endif
                }
                let expected = marked(sample.expected)
                var differences: [String] = []
                if passage.context != expected.0 { differences.append("source=\(passage.context.debugDescription), block=\(String(describing: passage.nearbyContext))") }
                if passage.selection != expected.1 { differences.append("selection=\(String(describing: passage.selection)), expected=\(String(describing: expected.1))") }
                let expectedQuery = sample.query ?? (expected.1.flatMap { Range($0, in: expected.0) }.map { String(expected.0[$0]) } ?? "")
                if passage.text != expectedQuery { differences.append("query=\(passage.text)") }
                if passage.structure.rawValue != sample.structure { differences.append("structure=\(passage.structure)") }
                if LookupPolicy(passage).automaticallyTranslatesContext != sample.automatic { differences.append("automatic=\(LookupPolicy(passage).automaticallyTranslatesContext)") }
                #if !BOUNDARY_BASELINE
                if passage.extent.rawValue != sample.extent { differences.append("extent=\(passage.extent)") }
                if let selection = passage.selection, let range = Range(selection, in: passage.context), passage.context[range] != passage.text {
                    differences.append("query does not match its exact source span")
                }
                #endif
                if !differences.isEmpty { failures.append(name + ": " + differences.joined(separator: "; ")) }
            } catch { failures.append(name + ": \(error)") }
        }
        for sample in corpus.cases {
            check(sample)
            #if !BOUNDARY_BASELINE
            if sample.mode == "ocr" {
                for scale in [1.5, 2.0] { check(sample, scale: scale, dx: -600, dy: 240, reversed: true) }
            }
            if sample.reflow == true {
                let words = sample.expected.split(separator: " ").map(String.init)
                for width in [3, 5, 7] {
                    let wrapped = words.enumerated().map { i, word in (i > 0 ? (i % width == 0 ? "\n" : " ") : "") + word }.joined()
                    check(sample, text: wrapped)
                }
            }
            #endif
        }
        for failure in failures { print("FAIL " + failure) }
        print("Boundary corpus: \(count - failures.count)/\(count) passed; \(corpus.cases.count) base cases; \(Set(corpus.cases.map(\.category)).count) categories.")
        #if !BOUNDARY_BASELINE
        try await checkCaptureAndStorage()
        try checkVision()
        try await MixedWrapTests.run()
        #endif
        if let report = ProcessInfo.processInfo.environment["WAX_BOUNDARY_REPORT"] {
            try FileManager.default.createDirectory(at: URL(fileURLWithPath: report).deletingLastPathComponent(), withIntermediateDirectories: true)
            let data = try JSONSerialization.data(withJSONObject: ["baseCases": corpus.cases.count, "checks": count,
                "passed": count - failures.count, "failures": failures, "categories": Array(Set(corpus.cases.map(\.category))).sorted()], options: [.prettyPrinted, .sortedKeys])
            try data.write(to: URL(fileURLWithPath: report))
        }
        if !failures.isEmpty { exit(1) }
    }

    #if !BOUNDARY_BASELINE
    static func checkVision() throws {
        struct VisionCase {
            let id: String
            let rows: [String]
            let expected: String
            var gap: CGFloat = 38
            var x: [CGFloat] = []
            var y: [CGFloat] = []
            var crop: String = ""
            var extent: ContextExtent = .complete
        }
        let samples = [
            VisionCase(id: "wrap", rows: ["The engineer checked the", "⟦sensor⟧ before starting the experiment."], expected: "The engineer checked the sensor before starting the experiment."),
            VisionCase(id: "negation", rows: ["Do not remove the ⟦sensor⟧", "until the experiment has finished."], expected: "Do not remove the sensor until the experiment has finished."),
            VisionCase(id: "comments", rows: ["// The engineer checked the", "// ⟦sensor⟧ before starting the experiment.", "const sensor = 1;"], expected: "The engineer checked the sensor before starting the experiment."),
            VisionCase(id: "list", rows: ["- Inspect the instrument and", "record the ⟦sensor⟧ temperature.", "- Replace the cable."], expected: "- Inspect the instrument and record the sensor temperature.", x: [60, 84, 60]),
            VisionCase(id: "paragraph", rows: ["An unrelated piece of information", "The ⟦sensor⟧ remains connected."], expected: "The sensor remains connected.", gap: 75),
            VisionCase(id: "columns", rows: ["The engineer checked the", "⟦sensor⟧ before starting the experiment.", "A different article is beside it.", "This text must never be included."], expected: "The engineer checked the sensor before starting the experiment.", x: [60, 60, 1000, 1000], y: [220, 182, 220, 182]),
            VisionCase(id: "abbreviation", rows: ["Dr. Chen checked the ⟦sensor⟧.", "Another test follows."], expected: "Dr. Chen checked the sensor."),
            VisionCase(id: "decimal", rows: ["Version 3.14.2 reports 2.5 units for the ⟦sensor⟧."], expected: "Version 3.14.2 reports 2.5 units for the sensor."),
            VisionCase(id: "clipped-start", rows: ["The engineer checked the", "⟦sensor⟧ before starting the experiment."], expected: "sensor before starting the experiment.", crop: "top", extent: .missingStart),
            VisionCase(id: "clipped-end", rows: ["The engineer checked the ⟦sensor⟧ before starting the experiment."], expected: "The engineer checked the sensor", crop: "right", extent: .missingEnd),
            VisionCase(id: "clipped-both", rows: ["The engineer checked the", "⟦sensor⟧ before starting the experiment"], expected: "sensor before starting the experiment", crop: "both", extent: .missingBoth)
        ]
        var observations: [[String: Any]] = []
        var visionFailures: [String] = []
        let destination = ProcessInfo.processInfo.environment["WAX_BOUNDARY_IMAGES"].map { URL(fileURLWithPath: $0, isDirectory: true) }
        if let destination { try FileManager.default.createDirectory(at: destination, withIntermediateDirectories: true) }
        for dark in [false, true] {
            let font: NSFont = dark ? .monospacedSystemFont(ofSize: 26, weight: .regular) : .systemFont(ofSize: 22)
            let attributes: [NSAttributedString.Key: Any] = [.font: font, .foregroundColor: dark ? NSColor.white : NSColor.black]
            for sample in samples {
                let canvas = CGSize(width: 1600, height: 320)
                let image = NSImage(size: canvas)
                image.lockFocus()
                (dark ? NSColor.black : NSColor.white).setFill()
                CGRect(origin: .zero, size: canvas).fill()
                var point = CGPoint.zero, selectedEnd: CGFloat = 0, selectedY: CGFloat = 0
                for (i, raw) in sample.rows.enumerated() {
                    let source = marked(raw), x = sample.x.isEmpty ? 60 : sample.x[i]
                    let y = sample.y.isEmpty ? 220 - CGFloat(i) * sample.gap : sample.y[i]
                    (source.0 as NSString).draw(at: CGPoint(x: x, y: y), withAttributes: attributes)
                    if let hit = source.1, let range = Range(hit, in: source.0) {
                        let prefix = (String(source.0[..<range.lowerBound]) as NSString).size(withAttributes: attributes).width
                        let width = (String(source.0[range]) as NSString).size(withAttributes: attributes).width
                        point = CGPoint(x: x + prefix + width / 2, y: y + font.pointSize * 0.55)
                        selectedEnd = x + prefix + width
                        selectedY = y
                    }
                }
                image.unlockFocus()
                guard let full = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else { throw CocoaError(.fileReadUnknown) }
                var bounds = CGRect(origin: .zero, size: canvas)
                if sample.crop == "right" { bounds.size.width = selectedEnd + 5 }
                if sample.crop == "top" || sample.crop == "both" { bounds.size.height = selectedY + font.pointSize + 6 }
                if sample.crop == "both" { bounds.origin.y = selectedY - 5; bounds.size.height = font.pointSize + 11 }
                let sx = CGFloat(full.width) / canvas.width, sy = CGFloat(full.height) / canvas.height
                let pixels = CGRect(x: bounds.minX * sx, y: (canvas.height - bounds.maxY) * sy, width: bounds.width * sx, height: bounds.height * sy)
                guard let bitmap = full.cropping(to: pixels) else { throw CocoaError(.fileReadUnknown) }
                let name = sample.id + (dark ? "-dark-mono" : "-light-system")
                if let destination, let png = NSBitmapImageRep(cgImage: bitmap).representation(using: .png, properties: [:]) {
                    try png.write(to: destination.appendingPathComponent(name + ".png"))
                }
                let passage = try Reader.recognize(image: bitmap, target: CGPoint(x: (point.x - bounds.minX) / bounds.width,
                                                                                y: (point.y - bounds.minY) / bounds.height), language: "en", isCrop: true)
                observations.append(["case": name, "source": passage.context, "word": passage.text, "extent": passage.extent.rawValue,
                                     "selection": passage.selection.map { [$0.location, $0.length] } ?? [], "automatic": LookupPolicy(passage).automaticallyTranslatesContext])
                print("Vision boundary", name, "→", passage.extent, passage.context)
                let punctuationLostSafely = sample.extent == .complete && passage.extent == .uncertain &&
                    sample.expected.hasSuffix(".") && passage.context == String(sample.expected.dropLast()) &&
                    !LookupPolicy(passage).automaticallyTranslatesContext
                if punctuationLostSafely { print("Vision safe fallback: OCR omitted sentence-final punctuation; no punctuation was fabricated.") }
                if !(passage.text == "sensor" && ((passage.context == sample.expected && passage.extent == sample.extent &&
                    LookupPolicy(passage).automaticallyTranslatesContext == (sample.extent == .complete)) || punctuationLostSafely)) {
                    visionFailures.append("\(name): \(passage.context), \(passage.extent)")
                }
            }
        }
        if let destination {
            try JSONSerialization.data(withJSONObject: observations, options: [.prettyPrinted, .sortedKeys]).write(to: destination.appendingPathComponent("observations.json"))
        }
        if !visionFailures.isEmpty { throw NSError(domain: "VisionBoundary", code: 1, userInfo: [NSLocalizedDescriptionKey: visionFailures.joined(separator: "\n")]) }
        print("Passed: \(observations.count) real Vision boundary/crop checks (including explicitly recorded safe punctuation-loss fallbacks); offscreen synthetic text only.")
    }

    static func checkCaptureAndStorage() async throws {
        func require(_ value: Bool, _ message: String) throws {
            if !value { throw NSError(domain: "BoundaryAcceptance", code: 1, userInfo: [NSLocalizedDescriptionKey: message]) }
        }
        let partial = Passage(text: "sensor", context: "checked the sensor", language: "en", extent: .missingBoth)
        let full = Passage(text: "sensor", context: "The engineer checked the sensor before the experiment.", language: "en")
        var attempts = 0
        let recovered = try await ContextCapture.complete(partial) { attempts += 1; return full }
        try require(attempts == 1 && recovered == full, "A clipped capture should recover once.")
        attempts = 0
        _ = try await ContextCapture.complete(full) { attempts += 1; return partial }
        try require(attempts == 0, "A complete sentence must not trigger optional capture.")
        let changed = try await ContextCapture.complete(partial) { Passage(text: "cable", context: "The cable is connected.", language: "en") }
        try require(changed == partial, "A different pointed word must not replace the original.")
        let unavailable = try await ContextCapture.complete(partial) { throw CocoaError(.fileReadUnknown) }
        try require(unavailable == partial, "An optional capture error must retain the original.")
        attempts = 0
        let pending = Task {
            try await ContextCapture.complete(partial) {
                attempts += 1
                try await Task.sleep(nanoseconds: 3_000_000_000)
                return full
            }
        }
        while attempts == 0 { await Task.yield() }
        pending.cancel()
        do { _ = try await pending.value; try require(false, "Cancelled capture returned a stale result.") }
        catch is CancellationError { }
        try require(attempts == 1, "Cancellation must not start more captures.")
        let screen = CGRect(x: -1600, y: -300, width: 1600, height: 1000)
        for point in [CGPoint(x: -1599, y: -299), CGPoint(x: -1, y: 699), CGPoint(x: -800, y: 200)] {
            let initial = Reader.hoverRect(at: point, on: screen), expanded = Reader.expandedHoverRect(at: point, on: screen)
            try require(screen.contains(expanded) && expanded.contains(initial) && expanded.width <= 1200 && expanded.height <= 480,
                        "Expansion must stay bounded on the original display, including negative coordinates.")
        }
        let cache = LookupCache()
        cache.insert(LookupResult(meaning: "传感器", origin: .sentence, sentenceTranslation: "完整句译"), for: full)
        let sameTextPartial = Passage(text: full.text, context: full.context, language: "en", extent: .missingStart)
        try require(cache.result(for: sameTextPartial) == nil, "Incomplete evidence must not reuse the full-context cache.")
        cache.insert(LookupResult(meaning: "句中含义", origin: .sentence), for: partial)
        try require(cache.result(for: partial) == nil, "A partial capture cannot be cached as aligned sentence meaning.")
        let suite = "WaxTranslate.Test.boundary." + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let book = Notebook(defaults: defaults)
        _ = book.save(partial, translation: "传感器", origin: "dictionary")
        _ = book.recordLookup(partial, meaning: "传感器")
        let restored = Notebook(defaults: defaults)
        try require(restored.entries.first?.passage.extent == .missingBoth && restored.recent.first?.passage.value.extent == .missingBoth,
                    "Saved and recent evidence must retain completeness.")
        try require(SentenceExcerpt(partial).passage.extent == .missingBoth && partial.using(language: "fr").extent == .missingBoth,
                    "Excerpt and language changes must not discard completeness.")
        let legacy = Entry(id: UUID(), source: "sensor", target: "传感器", context: full.context, sentenceTranslation: nil, due: Date(), streak: 2)
        let decoded = try JSONDecoder().decode(Entry.self, from: JSONEncoder().encode(legacy))
        try require(decoded.passage.extent == .complete && decoded.streak == 2, "Legacy entries retain meaning and review state.")
        let code = Passage(text: "INTEGER", context: "let field: INTEGER", language: "en", structure: .code)
        _ = book.save(code, translation: "整数类型", origin: "term")
        _ = book.recordLookup(code, meaning: "整数类型")
        let codeBook = Notebook(defaults: defaults)
        try require(codeBook.entries.first?.passage.structure == .code && codeBook.recent.first?.passage.value.structure == .code,
                    "Current records must restore code structure.")
        struct LegacyView: Decodable {
            enum Structure: String, Decodable { case sentence, list, title, path, fragment }
            let structure: Structure?
            let source, target: String
        }
        let oldView = try JSONDecoder().decode(LegacyView.self, from: JSONEncoder().encode(codeBook.entries[0]))
        try require(oldView.structure == .fragment && oldView.source == "INTEGER" && oldView.target == "整数类型",
                    "An older decoder must still read records after rollback; new code kinds use a safe legacy fallback.")
        print("Passed: bounded capture recovery/cancellation, changed-screen rejection, source maps, completeness cache isolation and legacy/save/recent persistence.")
    }
    #endif
}
