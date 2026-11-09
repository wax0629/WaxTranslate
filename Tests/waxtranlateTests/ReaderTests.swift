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
    static func main() async {
        do { try await run() }
        catch {
            FileHandle.standardError.write(Data("Failed: \(error)\n".utf8))
            exit(1)
        }
    }

    private static func run() async throws {
        let ruledOut = try testHoverAndRegion("These results do not rule out infection.", expected: "rule out")
        let ranOut = try testHoverAndRegion("The device ran out of memory before the test ended.", expected: "ran out of")
        try testSecondaryDisplayCoordinates()
        try testCaptureBand()
        try testWrappedOCRInTwoColumns()
        try testSentenceAtExactOccurrence()
        try testPhraseAtExactOccurrence()
        try testConciseGloss()
        try testSavingAndReview(ruledOut)
        try testLanguageRouting()
        try testActivityAndCorruptData(ruledOut)
        try testReadingCancellation()
        try testReferenceBoundary()
        try testTerminology()
        try testPackedOCRAndManualLanguages()
        try await testInstalledTranslation(ruledOut: ruledOut, ranOut: ranOut)
        print("Passed: capture geometry, OCR, packed typography, phrase selection, exact occurrences, vocabulary migration, review, language routing, dashboard persistence, corrupt-data preservation, reading cancellation, local terminology and reference boundaries.")
    }

    static func testHoverAndRegion(_ sentence: String, anchor: String = "out", expected: String) throws -> Passage {
        let attributes: [NSAttributedString.Key: Any] = [.font: NSFont.systemFont(ofSize: 32), .foregroundColor: NSColor.black]
        let size = CGSize(width: ceil((sentence as NSString).size(withAttributes: attributes).width) + 60, height: 90)
        let image = NSImage(size: size)
        image.lockFocus()
        NSColor.white.setFill()
        CGRect(origin: .zero, size: size).fill()
        let origin = CGPoint(x: 25, y: 20)
        (sentence as NSString).draw(at: origin, withAttributes: attributes)
        image.unlockFocus()
        let bitmap = try require(image.cgImage(forProposedRect: nil, context: nil, hints: nil))
        let region = try Reader.recognize(image: bitmap, target: nil)
        try expect(region.text == sentence && region.context.isEmpty && !region.isPhrase)
        let range = try require(sentence.range(of: anchor))
        let prefix = String(sentence[..<range.lowerBound]) as NSString
        let x = origin.x + prefix.size(withAttributes: attributes).width + (anchor as NSString).size(withAttributes: attributes).width / 2
        let hit = try Reader.recognize(image: bitmap, target: CGPoint(x: x / size.width, y: 38 / size.height))
        try expect(hit.text == expected && hit.context == sentence && hit.isPhrase)
        try expect(hit.anchor == NSRange(range, in: sentence))
        try expect(hit.selection == (sentence as NSString).range(of: expected))
        let blank = try? Reader.recognize(image: bitmap, target: CGPoint(x: 0.95, y: 0.95))
        try expect(blank == nil)
        return hit
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

    static func testPhraseAtExactOccurrence() throws {
        let frame = CGRect(x: 20, y: 100, width: 280, height: 20)
        func hover(_ sentence: String, _ word: String, last: Bool = false) throws -> Passage {
            let hit = (sentence as NSString).range(of: word, options: last ? .backwards : [])
            return try SentenceContext.passage(in: [TextLine(text: sentence, frame: frame, hit: hit)])
        }

        let repeated = "We walked out to the garage and ruled out a leak."
        let first = try hover(repeated, "out")
        try expect(first.text == "out" && !first.isPhrase)
        let second = try hover(repeated, "out", last: true)
        try expect(second.text == "ruled out" && second.anchor == (repeated as NSString).range(of: "out", options: .backwards))
        let marked = try require(LookupTranslation.markedSentence(second))
        let bold = try require(marked.runs.first { $0.inlinePresentationIntent?.contains(.stronglyEmphasized) == true })
        try expect(String(marked[bold.range].characters) == "ruled out")
        try expect(try hover("We are looking up the number now.", "looking").text == "looking up")
        try expect(try hover("We have run out of water.", "of").text == "run out of")
        for sentence in [
            "The rule, out of date for years, still applies.",
            "Please carry the boxes out of the room.",
            "Dans cet exemple français, les mots « rule out » sont une citation étrangère."
        ] {
            try expect(try hover(sentence, "out").text == "out")
        }
        try expect(try hover("She looked the address up in the directory.", "up").text == "up")

        let line = TextLine(text: "These results rule", frame: frame, hit: NSRange(location: 14, length: 4))
        let right = TextLine(text: "out of order", frame: frame.offsetBy(dx: 540, dy: -27), hit: nil)
        try expect(try SentenceContext.passage(in: [line, right]).text == "rule")
        let below = TextLine(text: "out a leak.", frame: frame.offsetBy(dx: 0, dy: -27), hit: nil)
        let wrapped = try SentenceContext.passage(in: [right, line, below])
        try expect(wrapped.text == "rule out" && wrapped.context == "These results rule out a leak.")
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
        for (fragment, expected) in [("一下", nil), ("查一下", "查一下")] as [(String, String?)] {
            var translated = AttributedString(fragment)
            translated.inlinePresentationIntent = .stronglyEmphasized
            let sentence = AttributedString("请") + translated + AttributedString("地址。")
            try expect(LookupTranslation.alignedMeaning(in: sentence, isPhrase: true) == expected)
        }
    }

    static func testInstalledTranslation(ruledOut: Passage, ranOut: Passage) async throws {
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
        try expect(meanings[0].contains("岸") && meanings[1].contains("银行"))

        for passage in [ruledOut, ranOut] {
            let result = try await LookupTranslation.translate(passage, session: session, dictionary: CompactGloss.candidates(for: passage, language: "en"))
            let full = try require(result.sentenceTranslation)
            print("Vision →", passage.text, "→", result.meaning, "/", full)
            try expect(result.origin == .sentence)
            if passage == ruledOut {
                try expect(result.meaning.contains("排除") && ["不", "未", "无", "非"].contains(where: full.contains))
            } else {
                try expect(["用完", "耗尽", "用尽"].contains(where: result.meaning.contains))
            }
        }

        for (text, headword, meanings) in [
            ("Please look up the address before you leave.", "look up", ["查"]),
            ("Look up at the ceiling to see the stars.", "Look up", ["仰", "抬头", "向上"])
        ] {
            let hit = try testHoverAndRegion(text, anchor: "up", expected: headword)
            let result = try await LookupTranslation.translate(hit, session: session, dictionary: [])
            print("Vision →", hit.text, "→", result.meaning, "/", result.sentenceTranslation ?? "")
            try expect(result.origin == .sentence && meanings.contains(where: result.meaning.contains))
        }

        // Force plain translation with a stale span. “结束” belongs to ended, not memory.
        let unaligned = Passage(text: "memory", context: ranOut.context, selection: NSRange(location: 0, length: 3))
        let reference = try await LookupTranslation.translate(unaligned, session: session, dictionary: ["结束"])
        print("Unaligned memory →", reference.meaning, "/", reference.sentenceTranslation ?? "")
        try expect(reference.origin == .standalone && reference.meaning != "结束" && reference.sentenceTranslation != nil)
    }

    static func testSavingAndReview(_ passage: Passage) throws {
        let suite = UUID().uuidString
        let defaults = try require(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        let book = Notebook(defaults: defaults)
        book.save(passage, translation: "排除", sentenceTranslation: "这些结果并不排除感染。")
        book.save(passage, translation: "排除", sentenceTranslation: "这些结果并不排除感染。")
        try expect(book.entries.count == 1)
        let id = try require(book.entries.first?.id)
        book.review(id, remembered: true)
        let loaded = Notebook(defaults: defaults)
        let saved = try require(loaded.entries.first)
        try expect(saved.streak == 1 && saved.source == "rule out" && saved.context == passage.context)
        try expect(saved.displayMeaning == "排除" && saved.sentenceTranslation == "这些结果并不排除感染。")
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

    static func testLanguageRouting() throws {
        for word in ["tulip", "warehouse", "bank"] {
            try expect(Passage(text: word, context: word).sourceLanguage == "en")
        }
        for (text, expected) in [("これは日本語の文章です。", "ja"), ("이것은 한국어 문장입니다.", "ko"),
                                 ("Ceci est une phrase française.", "fr"), ("这是一个中文句子。", "zh")] {
            let detected = Passage(text: text, context: "").sourceLanguage
            try expect(detected.hasPrefix(expected))
        }
        let manual = Passage(text: "tulip", context: "tulip", language: "fr")
        try expect(manual.sourceLanguage == "fr")
        let text = "Please look up the address."
        let line = TextLine(text: text, frame: CGRect(x: 0, y: 0, width: 400, height: 20), hit: (text as NSString).range(of: "up"))
        try expect(try SentenceContext.passage(in: [line], language: "fr").text == "up")
    }

    static func testActivityAndCorruptData(_ phrase: Passage) throws {
        let suite = "WaxTranslate.Test." + UUID().uuidString
        let defaults = try require(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        let book = Notebook(defaults: defaults)
        let now = Date(timeIntervalSince1970: 1_700_000_000)
        try expect(book.totalLookups == 0 && book.recent.isEmpty)
        let first = try require(book.recordLookup(phrase, meaning: "排除", now: now))
        book.updateLookup(first, meaning: "排除感染")
        try expect(book.totalLookups == 1 && book.recent.first?.meaning == "排除感染")
        book.recordLookup(phrase, meaning: "排除", now: now.addingTimeInterval(1))
        try expect(book.totalLookups == 2 && book.recent.count == 1 && book.recent.first?.passage.value.isPhrase == true)
        for index in 0..<8 { book.recordLookup(Passage(text: "word\(index)", context: "", language: "en"), meaning: "释义", now: now) }
        try expect(book.recent.count == 6 && book.totalLookups == 10 && book.todayLookups(now: now) == 10)
        let tomorrow = Calendar.current.date(byAdding: .day, value: 1, to: now)!
        try expect(book.todayLookups(now: tomorrow) == 0)
        book.recordLookup(phrase, meaning: "排除", now: tomorrow)
        let loaded = Notebook(defaults: defaults)
        try expect(loaded.totalLookups == 11 && loaded.todayLookups(now: tomorrow) == 1 && loaded.recent.count == 6)
        try expect(loaded.save(phrase, translation: "排除"))
        let id = try require(loaded.entries.first?.id)
        for _ in 0..<3 { loaded.review(id, remembered: true, now: now) }
        try expect(loaded.masteredCount == 1 && loaded.dueCount(now: now) == 0)
        loaded.review(id, remembered: false, now: now)
        try expect(loaded.masteredCount == 0 && loaded.entries[0].due == now.addingTimeInterval(600))
        try expect(Notebook(defaults: defaults).entries[0].passage.isPhrase)
        let broken = Data("unreadable historical data".utf8)
        defaults.set(broken, forKey: "notebook.entries.v1")
        let corrupt = Notebook(defaults: defaults)
        try expect(corrupt.error != nil && !corrupt.save(phrase, translation: "排除"))
        try expect(defaults.data(forKey: "notebook.entries.v1") == broken)
        defaults.set(broken, forKey: "notebook.activity.v1")
        try expect(Notebook(defaults: defaults).recordLookup(phrase, meaning: "排除") == nil)
        try expect(defaults.data(forKey: "notebook.activity.v1") == broken)
    }

    static func testReadingCancellation() throws {
        let document = ReadingDocument()
        document.text = "First sentence."
        document.begin(language: "en")
        let old = try require(document.request)
        document.text = "Second sentence."
        document.complete(old, result: .success("过期译文"))
        try expect(document.translation.isEmpty && !document.busy && document.request == nil)
        document.begin(language: "en")
        let current = try require(document.request)
        document.complete(old, result: .success("又一条过期译文"))
        try expect(document.busy && document.translation.isEmpty)
        document.complete(current, result: .success("第二句话。"))
        try expect(!document.busy && document.translation == "第二句话。" && document.request == nil)
        document.cancel()
        document.complete(current, result: .success("取消后的旧译文"))
        try expect(document.translation.isEmpty && document.text == "Second sentence.")
        document.text = String(repeating: "a", count: 20001)
        document.begin(language: "en")
        try expect(document.request == nil && !document.busy)
        document.text = "这是一个中文句子。"
        document.begin(language: "zh-Hans")
        try expect(document.translationLanguage == "en")
    }

    static func testReferenceBoundary() throws {
        try expect(WordReferences.request(for: "full sentence with private context") == nil)
        try expect(WordReferences.request(for: String(repeating: "a", count: 97)) == nil)
        let request = try require(WordReferences.request(for: "Ghostty"))
        let query = try require(URLComponents(url: request.url!, resolvingAgainstBaseURL: false)?.queryItems)
        try expect(query.first(where: { $0.name == "search" })?.value == "Ghostty")
        let fixture = Data(#"{"search":[{"id":"Q123","description":"终端模拟器","match":{"text":"Ghostty"}},{"id":"Q456","description":"其他同名项","match":{"text":"Another"}},{"id":"../bad","description":"无效链接","match":{"text":"Ghostty"}}]}"#.utf8)
        let references = try WordReferences.parse(fixture, word: "Ghostty")
        try expect(references.count == 1 && references[0].id == "Q123")
    }

    static func testTerminology() throws {
        func passage(_ word: String, _ text: String, backwards: Bool = false) -> Passage {
            Passage(text: word, context: text, selection: (text as NSString).range(of: word, options: backwards ? .backwards : []), language: "en")
        }
        for (word, text, meaning) in [
            ("API", "The API returns a response.", "应用程序编程接口"),
            ("MVP", "We shipped an MVP to our users.", "最小可行产品"),
            ("MVP", "The player won the MVP award this season.", "最有价值球员"),
            ("Codex", "The developer used Codex to fix the repository.", "编程助手"),
            ("codex", "The ancient codex contains a medieval manuscript.", "手抄本"),
            ("Rust", "The service was written in Rust.", "编程语言"),
            ("MAR", "The mean annual rainfall (MAR) increased.", "mean annual rainfall"),
            ("widget", "We use widget to mean a reusable control.", "a reusable control")
        ] {
            let result = try require(LocalTerminology.lookup(passage(word, text)))
            try expect(result.meaning.contains(meaning))
        }
        try expect(LocalTerminology.lookup(passage("ram", "The ram ate grass.")) == nil)
        try expect(LocalTerminology.lookup(passage("Rust", "Rust appeared on the old gate.")) == nil)
        let text = "We shipped an MVP to users, while the player won an MVP this season."
        try expect(LocalTerminology.lookup(passage("MVP", text, backwards: true))?.meaning.contains("最有价值球员") == true)
        let article = "The mean annual rainfall (MAR) increased. This year's MAR was high."
        let hit = (article as NSString).range(of: "MAR", options: .backwards)
        let selected = TextLine(text: article, frame: CGRect(x: 0, y: 0, width: 1000, height: 20), hit: hit)
        let contextual = try SentenceContext.passage(in: [selected], language: "en")
        try expect(LocalTerminology.lookup(contextual)?.meaning == "mean annual rainfall")
    }

    static func testPackedOCRAndManualLanguages() throws {
        for font in [NSFont.systemFont(ofSize: 20), NSFont.systemFont(ofSize: 32),
                     NSFont(name: "Baskerville", size: 24)!, NSFont.monospacedSystemFont(ofSize: 24, weight: .regular)] {
            let fontSize = font.pointSize
            let text = "docs(logistics): warehouse/parcel; bank then bank."
            let attributes: [NSAttributedString.Key: Any] = [.font: font, .foregroundColor: NSColor.black]
            let width = ceil((text as NSString).size(withAttributes: attributes).width) + 50
            let image = NSImage(size: NSSize(width: width, height: 90))
            image.lockFocus()
            NSColor.white.setFill(); CGRect(x: 0, y: 0, width: width, height: 90).fill()
            (text as NSString).draw(at: NSPoint(x: 20, y: 20), withAttributes: attributes)
            image.unlockFocus()
            let pixels = try require(image.cgImage(forProposedRect: nil, context: nil, hints: nil))
            for word in ["docs", "logistics", "warehouse", "parcel", "bank"] {
                let range = try require(text.range(of: word, options: word == "bank" ? .backwards : []))
                let prefix = String(text[..<range.lowerBound]) as NSString
                let x = 20 + prefix.size(withAttributes: attributes).width + (word as NSString).size(withAttributes: attributes).width / 2
                let passage = try Reader.recognize(image: pixels, target: CGPoint(x: x / width, y: (20 + fontSize * 0.5) / 90), language: "en")
                guard passage.text == word && passage.sourceLanguage == "en" else {
                    throw CheckFailure(reason: "Packed OCR at \(fontSize)pt: expected \(word), got \(passage.text); \(passage.context)")
                }
                let selection = try require(passage.selection)
                try expect((passage.context as NSString).substring(with: selection) == word)
                if word == "bank" { try expect(selection == (passage.context as NSString).range(of: word, options: .backwards)) }
            }
        }
    }
}
