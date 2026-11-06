import AppKit
import NaturalLanguage
import Translation
private struct CheckFailure: Error {
    let reason: String
}

private func require<T>(_ value: T?, line: Int = #line) throws -> T {
    guard let value else { throw CheckFailure(reason: "Missing value at line \(line)") }
    return value
}

private func expect(_ condition: Bool, line: Int = #line) throws {
    guard condition else { throw CheckFailure(reason: "Failed check at line \(line)") }
}


@main @MainActor struct ReaderTests {
    static func main() async throws {
        try testWordAtPointerAndRegion()
        try testSecondaryDisplayCoordinates()
        try testCaptureBand()
        try testWrappedOCRInTwoColumns()
        try testSentenceAtExactOccurrence()
        try testConciseGloss()
        try testSavingAndReview()
        try await testInstalledTranslation()
        print("Passed: capture geometry, OCR, wrapped sentence in two columns, exact token alignment, concise glosses, vocabulary migration and review.")
    }

    static func testWordAtPointerAndRegion() throws {
        let size = CGSize(width: 580, height: 90)
        let image = NSImage(size: size)
        image.lockFocus()
        NSColor.white.setFill()
        CGRect(origin: .zero, size: size).fill()
        let attributes: [NSAttributedString.Key: Any] = [.font: NSFont.systemFont(ofSize: 40), .foregroundColor: NSColor.black]
        let origin = CGPoint(x: 25, y: 20)
        ("Hello world" as NSString).draw(at: origin, withAttributes: attributes)
        image.unlockFocus()
        let bitmap = try require(image.cgImage(forProposedRect: nil, context: nil, hints: nil))
        let region = try Reader.recognize(image: bitmap, target: nil)
        try expect(region.text == "Hello world")
        let x = origin.x + ("Hello wo" as NSString).size(withAttributes: attributes).width
        let hit = try Reader.recognize(image: bitmap, target: CGPoint(x: x/size.width, y: 40/size.height))
        try expect(hit == Passage(text: "world", context: "Hello world"))
        let blank = try? Reader.recognize(image: bitmap, target: CGPoint(x: 0.95, y: 0.95))
        try expect(blank == nil)
    }

    static func testSecondaryDisplayCoordinates() throws {
        try expect(Reader.displayRect(CGRect(x: -920, y: 1000, width: 80, height: 120), primaryHeight: 900) ==
                       CGRect(x: -920, y: -220, width: 80, height: 120))
    }

    static func testCaptureBand() throws {
        let display = CGRect(x: -1792, y: -100, width: 1792, height: 1120)
        let center = Reader.hoverRect(at: CGPoint(x: -1500, y: 460), on: display)
        try expect(center == CGRect(x: -1792, y: 320, width: 1792, height: 280))
        try expect(Reader.hoverRect(at: CGPoint(x: -1, y: 1019), on: display).maxY == display.maxY)
        try expect(Reader.hoverRect(at: CGPoint(x: -1791, y: -99), on: display).minY == display.minY)
    }

    static func testWrappedOCRInTwoColumns() throws {
        let size = CGSize(width: 1240, height: 190)
        let image = NSImage(size: size)
        image.lockFocus()
        NSColor.white.setFill()
        CGRect(origin: .zero, size: size).fill()
        let attributes: [NSAttributedString.Key: Any] = [.font: NSFont.systemFont(ofSize: 26), .foregroundColor: NSColor.black]
        let rows = ["It was sunny. They rested on the", "river bank before the long walk", "back to the village. Next came rain."]
        let side = ["A different article mentions fees.", "The bank approved the loan.", "Interest rates stayed the same."]
        for i in rows.indices {
            let y = CGFloat(124 - i * 36)
            (rows[i] as NSString).draw(at: CGPoint(x: 30, y: y), withAttributes: attributes)
            (side[i] as NSString).draw(at: CGPoint(x: 705, y: y), withAttributes: attributes)
        }
        image.unlockFocus()
        let bitmap = try require(image.cgImage(forProposedRect: nil, context: nil, hints: nil))
        let x = 30 + ("river ba" as NSString).size(withAttributes: attributes).width
        let hit = try Reader.recognize(image: bitmap, target: CGPoint(x: x / size.width, y: 101 / size.height))
        try expect(hit.text == "bank")
        try expect(hit.context == "They rested on the river bank before the long walk back to the village.")
    }

    static func testSentenceAtExactOccurrence() throws {
        let text = "First line. Check the first bank, then the second bank."
        let lastBank = (text as NSString).range(of: "bank", options: .backwards)
        let rows = [
            TextLine(text: text, frame: CGRect(x: 20, y: 140, width: 460, height: 20), hit: lastBank),
            TextLine(text: "Account balance", frame: CGRect(x: 565, y: 140, width: 150, height: 20), hit: nil),
            TextLine(text: "A separate paragraph.", frame: CGRect(x: 20, y: 70, width: 210, height: 20), hit: nil)
        ]
        let passage = try SentenceContext.passage(in: rows)
        try expect(passage.context == "Check the first bank, then the second bank.")
        try expect(passage.selection == (passage.context as NSString).range(of: "bank", options: .backwards))
        let marked = try require(LookupTranslation.markedSentence(passage))
        let emphasized = try require(marked.runs.first { $0.inlinePresentationIntent?.contains(.stronglyEmphasized) == true })
        try expect(String(marked.characters[..<emphasized.range.lowerBound]).hasSuffix("second "))
        let jp = [
            TextLine(text: "彼は川の", frame: CGRect(x: 12, y: 52, width: 80, height: 19), hit: nil),
            TextLine(text: "近くにいる。", frame: CGRect(x: 12, y: 27, width: 100, height: 19), hit: NSRange(location: 0, length: 2))
        ]
        try expect(try SentenceContext.passage(in: jp).context == "彼は川の近くにいる。")
    }

    static func testConciseGloss() throws {
        let raw = "novel | BrE test | A. noun ① (genre) 小说体 pinyin ② (book) 小说 novel B. adjective 新颖的 pinyin ‹idea›; 与众不同的 pinyin ▸ example 很长的例句"
        let glosses = CompactGloss.meanings(in: raw, partOfSpeech: "adjective")
        try expect(glosses.first == "新颖的" && !glosses.contains("很长的例句"))
        try expect(CompactGloss.meanings(in: "瞤 rún （瞤）〈文〉①动 眼皮跳动。").isEmpty)
        var gloss = AttributedString("河岸")
        gloss.inlinePresentationIntent = .stronglyEmphasized
        try expect(LookupTranslation.alignedMeaning(in: AttributedString("他们在") + gloss + AttributedString("上休息。")) == "河岸")
        var adjective = AttributedString("的新")
        adjective.inlinePresentationIntent = .stronglyEmphasized
        try expect(LookupTranslation.alignedMeaning(in: AttributedString("一种测量压力") + adjective + AttributedString("方法。")) == "新")
        try expect(LookupTranslation.alignedMeaning(in: gloss) == nil)
        try expect(LookupTranslation.alignedMeaning(in: gloss + AttributedString("和") + gloss) == nil)
    }

    static func testInstalledTranslation() async throws {
        let source = Locale.Language(identifier: "en")
        let target = Locale.Language(identifier: "zh-Hans")
        guard #available(macOS 26.4, *), await LanguageAvailability().status(from: source, to: target) == .installed else {
            print("Skipping live sentence alignment: requires macOS 26.4+ and installed EN/ZH languages.")
            return
        }
        let session = TranslationSession(installedSource: source, target: target)
        var meanings: [String] = []
        for sentence in ["They sat on the river bank and watched the water.", "She deposited her paycheck at the bank."] {
            let passage = Passage(text: "bank", context: sentence)
            let result = try await LookupTranslation.translate(passage, session: session, dictionary: CompactGloss.candidates(for: passage, language: "en"))
            let full = try require(result.sentenceTranslation)
            try expect(!result.meaning.isEmpty && result.meaning.count < 12 && full.count > result.meaning.count)
            meanings.append(result.meaning)
            print(sentence, "→", result.meaning, "/", full)
        }
        try expect(meanings[0] != meanings[1])
    }

    static func testSavingAndReview() throws {
        let suite = UUID().uuidString
        let defaults = try require(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        let book = Notebook(defaults: defaults)
        let passage = Passage(text: "word", context: "a word")
        book.save(passage, translation: "词", sentenceTranslation: "一个词")
        book.save(passage, translation: "词", sentenceTranslation: "一个词")
        try expect(book.entries.count == 1)
        let id = try require(book.entries.first?.id)
        book.review(id, remembered: true)
        let loaded = Notebook(defaults: defaults)
        try expect(loaded.entries.first?.streak == 1)
        try expect(loaded.entries.first?.sentenceTranslation == "一个词")
        let due = try require(loaded.entries.first?.due)
        try expect(due > Date())
        loaded.remove(id)
        try expect(Notebook(defaults: defaults).entries.isEmpty)
        let old: [String: Any] = [
            "id": UUID().uuidString, "source": "emergent", "target": "emergent | BrE example | adjective 新兴的 pinyin; 新生的 pinyin",
            "context": "An emergent property.", "due": 0, "streak": 2
        ]
        defaults.set(try JSONSerialization.data(withJSONObject: [old]), forKey: "notebook.entries.v1")
        let legacy = try require(Notebook(defaults: defaults).entries.first)
        try expect(legacy.streak == 2 && legacy.sentenceTranslation == nil && legacy.displayMeaning == "新兴的")
    }
}
