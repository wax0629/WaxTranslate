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
        try testContextExcerpt()
        try testCardPolicy()
        try testSavingAndReview(ruledOut)
        try testLanguageRouting()
        try testActivityAndCorruptData(ruledOut)
        try testReadingCancellation()
        try testReferenceBoundary()
        try testTerminology()
        try testMixedTerminology()
        try testPackedOCRAndManualLanguages()
        try testSmallMixedText()
        try testShortcutAndDockPreferences()
        try testSimplifiedOutput()
        try testLookupCache()
        try await testInstalledTranslation(ruledOut: ruledOut, ranOut: ranOut)
        print("Passed: capture geometry, cursor-free Retina configuration, small mixed text, OCR, packed typography, phrase selection, exact occurrences, vocabulary migration, review, language routing, dashboard persistence, corrupt-data preservation, reading cancellation, mixed-language terminology, unchanged-result boundaries, verified gloss boundaries, bounded bilingual context, reference boundaries, Option tap guards and Dock preferences.")
    }

    static func testCardPolicy() throws {
        let document = "• 更新README文档\n• 模型输入的token与访问token含义不同。\n\n下一段API。"
        let range = NSRange(document.range(of: "token")!, in: document)
        let scoped = try SentenceContext.passage(in: document, selection: range, language: "zh-Hans")
        try expect(!scoped.context.contains("README") && !scoped.context.contains("下一段"))
        try expect(scoped.structure == .list && LocalTerminology.lookup(scoped)?.meaning.contains("词元") == true)
        let repeated = "模型输入的token与访问token含义不同。"
        let last = NSRange(repeated.range(of: "token", options: .backwards)!, in: repeated)
        try expect(LocalTerminology.lookup(Passage(text: "token", context: repeated, selection: last, language: "zh-Hans"))?.meaning.contains("令牌") == true)
        for (context, expected) in [("用Transformer实现OCR。", "神经网络"), ("变电站的transformer。", "变压器")] {
            let word = context.contains("Transformer") ? "Transformer" : "transformer"
            try expect(LocalTerminology.lookup(Passage(text: word, context: context, language: "zh-Hans"))?.meaning.contains(expected) == true)
        }
        let fragment = Passage(text: "token", context: "…输入token与…", language: "en", structure: .fragment)
        try expect(!LookupPolicy(fragment).automaticallyTranslatesContext)
        let path = try SentenceContext.passage(in: "Sources/waxtranlate/LookupTranslation.swift", selection: NSRange(location: 19, length: 17), language: "en")
        try expect(path.structure == .path && LookupPolicy(path).needsConfirmation)
        let suite = "WaxTranslate.Test.rules." + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let book = Notebook(defaults: defaults)
        _ = book.save(scoped, translation: "词元", sentenceTranslation: "Only this item.", origin: "term")
        let restored = Notebook(defaults: defaults).entries[0]
        try expect(restored.passage.structure == .list && restored.origin == "term" && !restored.context.contains("README"))
        let voice = Passage(text: "VoiceOver", context: "人工听音与VoiceOver。", language: "zh-Hans")
        try expect(LookupPolicy(voice).needsConfirmation)
        let confirmed = LookupPolicy(Passage(text: "VoiceOver", context: "macOS辅助功能中的VoiceOver。", language: "zh-Hans"))
        try expect(confirmed.term?.meaning.contains("屏幕朗读") == true && !confirmed.defaultsToContext)
        let readme = LookupPolicy(Passage(text: "README", context: "更新README和开发文档。", language: "zh-Hans"))
        try expect(readme.term != nil && !readme.automaticallyTranslatesContext)
        let context = "用Docker部署Redis，通过API访问缓存。"
        for word in ["Docker", "Redis", "API"] {
            let policy = LookupPolicy(Passage(text: word, context: context, language: "zh-Hans"))
            try expect(policy.term != nil && policy.defaultsToContext && !policy.automaticallyTranslatesContext)
            try expect(policy.headwordLanguage == "en")
        }
        try expect(LookupPolicy(Passage(text: "UnknownSDK", context: "用Docker部署UnknownSDK。", language: "zh-Hans")).needsConfirmation)
        try expect(!LookupPolicy(Passage(text: "INTEGER", context: "INTEGER代表整数。", language: "zh-Hans")).needsConfirmation)
        try expect(LookupPolicy(Passage(text: "bank", context: "They sat on the river bank.", language: "en")).automaticallyTranslatesContext)
        let lines = [TextLine(text: "• 更新README文档", frame: CGRect(x: 0, y: 60, width: 180, height: 16), hit: NSRange(location: 4, length: 6)),
                     TextLine(text: "• 下一条API说明", frame: CGRect(x: 0, y: 36, width: 180, height: 16), hit: nil)]
        let selected = try SentenceContext.passage(in: lines, language: "zh-Hans")
        try expect(!selected.context.contains("下一条"))
        let title = "ア・サマア・バケイション"
        let titleLines = [TextLine(text: title, frame: CGRect(x: 0, y: 70, width: 400, height: 32), hit: NSRange(location: 2, length: 2)),
                          TextLine(text: "专辑：ランプ幻想", frame: CGRect(x: 0, y: 40, width: 220, height: 17), hit: nil)]
        let titleHit = try SentenceContext.passage(in: titleLines)
        try expect(titleHit.text == title && titleHit.context == title && titleHit.sourceLanguage == "ja")
        let englishTitle = try SentenceContext.passage(in: [TextLine(text: "A Summer Vacation", frame: CGRect(x: 0, y: 70, width: 400, height: 32), hit: NSRange(location: 2, length: 6)), titleLines[1]], language: "en")
        try expect(englishTitle.structure == .title && englishTitle.text == "Summer" && !LookupPolicy(englishTitle).automaticallyTranslatesContext)
        let mixedResult = LookupTranslation.makeResult(for: Passage(text: "integer", context: "顯示integer。", language: "zh-Hans"), meaning: "整數", origin: .standalone)
        try expect(mixedResult.meaning == "整数")
        let prose = [TextLine(text: "サマー・キャンプに参加した。", frame: CGRect(x: 0, y: 40, width: 300, height: 18), hit: NSRange(location: 0, length: 3))]
        let proseHit = try SentenceContext.passage(in: prose)
        try expect(proseHit.text == "サマー")
    }

    static func testLookupCache() throws {
        let cache = LookupCache(capacity: 2), now = Date(timeIntervalSince1970: 1_000)
        let first = Passage(text: "bank", context: "bank then bank", selection: NSRange(location: 0, length: 4), language: "en")
        let second = Passage(text: "bank", context: "bank then bank", selection: NSRange(location: 10, length: 4), language: "en")
        let differentLanguage = first.using(language: "de")
        cache.insert(LookupResult(meaning: "岸边", origin: .sentence), for: first, now: now)
        try expect(cache.result(for: first, now: now)?.meaning == "岸边")
        try expect(cache.result(for: second, now: now) == nil && cache.result(for: differentLanguage, now: now) == nil)
        cache.insert(LookupResult(meaning: "银行", origin: .sentence), for: second, now: now)
        _ = cache.result(for: first, now: now)
        cache.insert(LookupResult(meaning: "德语参考", origin: .standalone), for: differentLanguage, now: now)
        try expect(cache.result(for: second, now: now) == nil && cache.result(for: first, now: now) != nil)
        try expect(cache.result(for: first, now: now.addingTimeInterval(601)) == nil)
        let oversized = Passage(text: String(repeating: "a", count: 1001), context: "", language: "en")
        cache.insert(LookupResult(meaning: "参考", origin: .region), for: oversized, now: now)
        try expect(cache.result(for: oversized, now: now) == nil)
        let long = Passage(text: "magpie", context: String(repeating: "a long walk through the garden ", count: 12) + "magpie", language: "en")
        cache.insert(LookupResult(meaning: "喜鹊", origin: .sentence, excerptTranslation: "花园里的喜鹊"), for: long, now: now)
        try expect(cache.result(for: long, now: now) == nil)
        cache.insert(LookupResult(meaning: "喜鹊", origin: .sentence, sentenceTranslation: "完整句译", excerptTranslation: "节选译文"), for: long, now: now)
        try expect(cache.result(for: long, now: now)?.excerptTranslation == "节选译文")
    }

    static func testSimplifiedOutput() throws {
        try expect(TranslationOutput.normalize("整數與資料庫") == "整数与资料库")
        try expect(TranslationOutput.normalize("整數", target: "en") == "整數")
        try expect(TranslationOutput.normalize("體", target: "ja") == "體")
        try expect(CompactGloss.meanings(in: "integer | A. noun 整數").first == "整数")
        let domain = "WaxTranslate.Test.script." + UUID().uuidString
        let defaults = try require(UserDefaults(suiteName: domain))
        defer { defaults.removePersistentDomain(forName: domain) }
        let book = Notebook(defaults: defaults)
        let passage = Passage(text: "integer", context: "An integer is a whole number.", language: "en")
        try expect(book.save(passage, translation: "整數", sentenceTranslation: "整數是整的數。"))
        let saved = try require(Notebook(defaults: defaults).entries.first)
        try expect(saved.target == "整数" && saved.displaySentenceTranslation == "整数是整的数。")
        let document = ReadingDocument()
        document.text = "An integer is a whole number."
        document.begin(language: "en")
        let request = try require(document.request)
        document.complete(request, result: .success("整數是整的數。"))
        try expect(document.translation == "整数是整的数。")
        let reference = Data(#"{"search":[{"id":"Q1","description":"整數運算","match":{"text":"integer"}}]}"#.utf8)
        try expect(try WordReferences.parse(reference, word: "integer").first?.description == "整数运算")
    }

    static func testShortcutAndDockPreferences() throws {
        let domain = "WaxTranslate.Test.preferences." + UUID().uuidString
        let defaults = try require(UserDefaults(suiteName: domain))
        defer { defaults.removePersistentDomain(forName: domain) }
        let fresh = Preferences(defaults: defaults)
        try expect(fresh.shortcut == .option && !fresh.showInDock)
        fresh.shortcut = .controlOption
        fresh.showInDock = true
        let reloaded = Preferences(defaults: defaults)
        try expect(reloaded.shortcut == .controlOption && reloaded.showInDock)
        reloaded.showInDock = false
        try expect(!Preferences(defaults: defaults).showInDock)
        defaults.set("optionShift", forKey: "capture.shortcut")
        try expect(Preferences(defaults: defaults).shortcut == .optionShift)

        var tap = OptionTapTracker()
        func event(_ down: Bool, _ time: Double, keys: UInt32 = 10, pointer: UInt32 = 20,
                   modifiers: UInt32, blocked: Bool = false) -> Bool {
            tap.update(optionDown: down, blocked: blocked, time: time, keys: keys, pointer: pointer, modifiers: modifiers)
        }
        try expect(!event(true, 1, modifiers: 1))
        try expect(event(false, 1.12, modifiers: 2))
        try expect(!event(false, 1.15, modifiers: 2)) // release never repeats
        _ = event(true, 2, modifiers: 3)
        try expect(!event(false, 2.1, keys: 11, modifiers: 4)) // Option + letter
        _ = event(true, 3, modifiers: 5)
        try expect(!event(false, 3.1, pointer: 21, modifiers: 6)) // click / drag / scroll
        _ = event(true, 4, modifiers: 7)
        try expect(!event(false, 5, modifiers: 8)) // long hold
        _ = event(true, 6, modifiers: 9)
        _ = event(true, 6.05, modifiers: 10, blocked: true) // Shift pressed
        _ = event(true, 6.1, modifiers: 11) // releasing Shift must not rearm
        try expect(!event(false, 6.15, modifiers: 12))
        _ = event(true, 7, modifiers: 13, blocked: true) // key already held
        try expect(!event(false, 7.1, modifiers: 14))
        _ = event(true, 8, modifiers: .max)
        try expect(event(false, 8.1, modifiers: 0)) // counter wraps
        _ = event(true, 9, modifiers: 15)
        tap = OptionTapTracker() // changing mode discards pending tap
        try expect(!event(false, 9.1, modifiers: 16))
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
        let screen = CGRect(x: -1440, y: 900, width: 1440, height: 900)
        let bounds = CGRect(x: -920, y: 1000, width: 80, height: 120)
        try expect(Reader.sourceRect(bounds, on: screen) == CGRect(x: 520, y: 680, width: 80, height: 120))
        for scale: CGFloat in [1, 2] {
            let config = Reader.screenshotConfiguration(bounds: bounds, screen: screen, scale: scale)
            try expect(config.sourceRect == CGRect(x: 520, y: 680, width: 80, height: 120))
            try expect(config.width == Int(80 * scale) && config.height == Int(120 * scale) && !config.showsCursor)
        }
    }

    static func testSmallMixedText() throws {
        let sentence = "在 Codex 中阅读 English text，按 Option 查词。"
        for size: CGFloat in [12, 14, 18] {
            for dark in [false, true] {
                let font = NSFont.systemFont(ofSize: size)
                let attributes: [NSAttributedString.Key: Any] = [.font: font, .foregroundColor: dark ? NSColor.white : NSColor.black]
                let canvas = NSSize(width: 600, height: 90)
                let image = NSImage(size: canvas)
                image.lockFocus()
                (dark ? NSColor.black : NSColor.white).setFill()
                NSRect(origin: .zero, size: canvas).fill()
                (sentence as NSString).draw(at: NSPoint(x: 20, y: 25), withAttributes: attributes)
                image.unlockFocus()
                let bitmap = try require(image.cgImage(forProposedRect: nil, context: nil, hints: nil))
                for word in ["Codex", "English", "Option"] {
                    let range = try require(sentence.range(of: word))
                    let prefix = String(sentence[..<range.lowerBound]) as NSString
                    let x = 20 + prefix.size(withAttributes: attributes).width + (word as NSString).size(withAttributes: attributes).width / 2
                    let result = try Reader.recognize(image: bitmap, target: CGPoint(x: x / canvas.width,
                                      y: (25 + font.ascender * 0.55) / canvas.height))
                    try expect(result.text.caseInsensitiveCompare(word) == .orderedSame)
                }
                let empty = try? Reader.recognize(image: bitmap, target: CGPoint(x: 0.9, y: 0.8))
                try expect(empty == nil)
            }
        }
    }

    static func testCaptureBand() throws {
        let display = CGRect(x: -1792, y: -100, width: 1792, height: 1120)
        let center = Reader.hoverRect(at: CGPoint(x: -1500, y: 460), on: display)
        try expect(center == CGRect(x: -1792, y: 370, width: 900, height: 180))
        try expect(Reader.hoverRect(at: CGPoint(x: -1, y: 500), on: display).maxX == display.maxX)
        try expect(Reader.hoverRect(at: CGPoint(x: -1, y: 1019), on: display).maxY == display.maxY)
        try expect(Reader.hoverRect(at: CGPoint(x: -1791, y: -99), on: display).minY == display.minY)
        let small = CGRect(x: 100, y: 100, width: 600, height: 400)
        try expect(Reader.hoverRect(at: CGPoint(x: 500, y: 300), on: small) == CGRect(x: 100, y: 250, width: 600, height: 100))
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
        try expect(LookupTranslation.alignedMeaning(in: AttributedString("一种测量压力") + adjective + AttributedString("方法。")) == "的新")
        for (gloss, reference, expected) in [("喜鹊中", "喜鹊", "喜鹊"), ("在喜鹊", "喜鹊", "喜鹊"),
            ("的新", "新", "新"), ("河岸上", "河岸", "河岸"), ("喜鵲中", "喜鹊", "喜鹊"),
            ("进行中", "进行中", "进行中"), ("中国", "中国", "中国"), ("的确", "的确", "的确")] {
            try expect(LookupTranslation.verifiedBoundaryMeaning(gloss, references: [reference]) == expected)
        }
        for (gloss, reference) in [("中国", "国"), ("地中海", "海"), ("中医", "医"), ("喜鹊种群中", "喜鹊"), ("在河岸", "银行")] {
            try expect(LookupTranslation.verifiedBoundaryMeaning(gloss, references: [reference]) == nil)
        }
        try expect(LookupTranslation.needsBoundaryVerification("喜鹊中") && LookupTranslation.needsBoundaryVerification("在喜鹊"))
        try expect(!LookupTranslation.needsBoundaryVerification("中国") && !LookupTranslation.needsBoundaryVerification("的确"))
        try expect(LookupTranslation.alignedMeaning(in: gloss) == nil)
        try expect(LookupTranslation.alignedMeaning(in: gloss + AttributedString("和") + gloss) == nil)
        for (fragment, expected) in [("一下", nil), ("查一下", "查一下")] as [(String, String?)] {
            var translated = AttributedString(fragment)
            translated.inlinePresentationIntent = .stronglyEmphasized
            let sentence = AttributedString("请") + translated + AttributedString("地址。")
            try expect(LookupTranslation.alignedMeaning(in: sentence, isPhrase: true) == expected)
        }
    }

    static func testContextExcerpt() throws {
        let short = Passage(text: "magpie", context: "I saw a magpie in the garden.", language: "en")
        try expect(!SentenceExcerpt(short).isTruncated && SentenceExcerpt(short).passage == short)
        let long = "A magpie watched quietly while " + String(repeating: "the visitors walked slowly through the garden, ", count: 5) + "another magpie in the tree began to sing near the old house."
        for range in [long.range(of: "magpie")!, long.range(of: "magpie", options: .backwards)!] {
            let original = Passage(text: "magpie", context: long, selection: NSRange(range, in: long), language: "en")
            let excerpt = SentenceExcerpt(original)
            try expect(excerpt.isTruncated && excerpt.passage.context.count <= 181)
            let selection = try require(excerpt.passage.selection.flatMap { Range($0, in: excerpt.passage.context) })
            try expect(excerpt.passage.context[selection] == "magpie" && excerpt.passage.context.contains("another") == (range == long.range(of: "magpie", options: .backwards)!))
            try expect(LookupTranslation.markedSentence(excerpt.passage) != nil && original.context == long)
        }
        for word in ["Beginning", "ending"] {
            let sentence = "Beginning " + String(repeating: "a word with context ", count: 20) + "ending."
            let excerpt = SentenceExcerpt(Passage(text: word, context: sentence, language: "en"))
            try expect(excerpt.isTruncated && excerpt.passage.context.count <= 181 && LookupTranslation.markedSentence(excerpt.passage) != nil)
        }
        let chinese = String(repeating: "🪶这里的文字用于测试长句上下文，", count: 12) + "这里用OCR识别图片中的文字。"
        let mixed = SentenceExcerpt(Passage(text: "OCR", context: chinese, language: "zh-Hans"))
        try expect(mixed.isTruncated && mixed.passage.context.count <= 91 && mixed.passage.sourceLanguage == "zh-Hans")
        try expect(LookupTranslation.markedSentence(mixed.passage) != nil)
        let phraseContext = String(repeating: "They checked the data carefully, ", count: 8) + "but could not rule out infection."
        let phrase = SentenceExcerpt(Passage(text: "rule out", context: phraseContext,
                                            anchor: NSRange(phraseContext.range(of: "out")!, in: phraseContext), language: "en"))
        try expect(phrase.passage.isPhrase && phrase.passage.context[Range(phrase.passage.anchor!, in: phrase.passage.context)!] == "out")
        let invalid = Passage(text: "magpie", context: long, selection: NSRange(location: 0, length: 3), language: "en")
        try expect(!SentenceExcerpt(invalid).isTruncated)
    }

    static func testInstalledTranslation(ruledOut: Passage, ranOut: Passage) async throws {
        let source = Locale.Language(identifier: "en")
        let target = Locale.Language(identifier: "zh-Hans")
        guard #available(macOS 26.4, *), await LanguageAvailability().status(from: source, to: target) == .installed else {
            print("Skipping live sentence alignment: requires macOS 26.4+ and installed EN/ZH languages.")
            return
        }
        let session = TranslationSession(installedSource: source, target: target)
        for context in ["In a magpie, the black and white feathers are easy to recognize.", "Among the magpie population, this behavior is common.", "I saw a magpie in the garden.", "The account is added to magpie."] {
            let result = try await LookupTranslation.translate(Passage(text: "magpie", context: context, language: "en"), session: session, dictionary: [])
            try expect(result.meaning == "喜鹊" && result.sentenceTranslation != nil)
            print("Boundary check →", result.meaning, "/", result.sentenceTranslation ?? "")
        }
        let long = Passage(text: "bank", context: "After a very long walk through the quiet village and past the old houses where people were preparing for the evening, they sat on the river bank and watched the water flow slowly toward the distant mountains.", language: "en")
        let longResult = try await LookupTranslation.translate(long, session: session, dictionary: [])
        // The service may drop word emphasis in this long sample. Its independent
        // word reference stays explicitly labeled; both context translations must
        // describe the actual river-bank sentence rather than the isolated word.
        try expect(longResult.isUsable && longResult.sentenceTranslation?.contains("岸") == true && longResult.excerptTranslation?.contains("岸") == true)
        print("Long context →", longResult.meaning, "origin:", longResult.origin, "/", longResult.excerptTranslation ?? "")
        let api = try await LookupTranslation.translate(Passage(text: "API", context: "The API returns a response.", language: "en"), session: session, dictionary: [])
        try expect(api.origin == .term && api.meaning.contains("应用程序编程接口") && api.sentenceTranslation != nil)
        for context in ["tulip", "A red tulip blooms in the garden."] {
            let passage = Passage(text: "tulip", context: context)
            try expect(passage.sourceLanguage == "en")
            let result = try await LookupTranslation.translate(passage, session: session,
                dictionary: CompactGloss.candidates(for: passage, language: "en"))
            try expect(result.meaning.contains("郁金香"))
            print(context, "→", result.meaning)
        }
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
        let chinese = Locale.Language(identifier: "zh-Hans")
        if await LanguageAvailability().status(from: chinese, to: source) == .installed {
            let mixedSession = TranslationSession(installedSource: chinese, target: source)
            for (word, context, expected) in [
                ("INTEGER", "已安装测试版本，INTEGER现在显示简体整数。", "整数"),
                ("LookupTranslation", "Sources/waxtranlate/LookupTranslation.swift", "名称组成词参考")
            ] {
                let sample = Passage(text: word, context: context, language: "zh-Hans")
                let result = try await LookupTranslation.translate(sample, session: mixedSession, dictionary: [])
                try expect(result.isUsable && result.meaning.contains(expected) && result.sentenceTranslation != nil)
                print("Live mixed context →", word, result.meaning, "/", result.sentenceTranslation ?? "")
            }
        } else { print("Skipping mixed context translation: ZH/EN languages not installed.") }
        let japanese = Locale.Language(identifier: "ja")
        if await LanguageAvailability().status(from: japanese, to: target) == .installed {
            let passage = Passage(text: "猫", context: "猫が眠っています。")
            try expect(passage.sourceLanguage == "ja")
            let japaneseSession = TranslationSession(installedSource: japanese, target: target)
            let result = try await LookupTranslation.translate(passage, session: japaneseSession, dictionary: [])
            let full = try require(result.sentenceTranslation)
            try expect(result.isUsable && result.meaning.contains("猫") && full.contains("猫") && ["睡", "眠"].contains(where: full.contains))
            print("Japanese →", result.meaning, "/", full)
        } else { print("Skipping live Japanese translation: JA/ZH languages not installed.") }
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
            try expect(LanguageResolver.resolve(word, englishDictionaryEvidence: false) == "en")
        }
        try expect(Passage(text: "tulip", context: "A red tulip blooms in the garden.").sourceLanguage == "en")
        for (word, expected) in [("bonjour", "fr"), ("gatto", "it"), ("hola", "es"), ("hallo", "de"),
                                 ("obrigado", "pt"), ("rumah", "id")] {
            try expect(LanguageResolver.resolve(word, englishDictionaryEvidence: false) == expected)
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

    static func testMixedTerminology() throws {
        func passage(_ word: String, _ context: String, language: String? = nil, last: Bool = false) -> Passage {
            Passage(text: word, context: context, selection: (context as NSString).range(of: word, options: last ? .backwards : []), language: language)
        }
        for (word, meaning) in [("OCR", "光学字符识别"), ("API", "应用程序编程接口"), ("SDK", "软件开发工具包"),
                                ("JSON", "数据格式"), ("CPU", "中央处理器"), ("BPE", "字节对编码"),
                                ("ＯＣＲ", "光学字符识别"), ("OCRs", "光学字符识别")] {
            let p = passage(word, "这里使用\(word)处理图片和代码，其他文字都是中文。")
            try expect(p.sourceLanguage.hasPrefix("zh"))
            let term = try require(LocalTerminology.lookup(p))
            try expect(term.meaning.contains(meaning))
            let old = LookupResult(meaning: word, origin: .standalone, sentenceTranslation: "Old English output")
            let initial = try require(LookupResult.initial(term: term, cached: old, dictionary: ["错误参考"]))
            try expect(initial.origin == .term && initial.meaning.contains(meaning) && initial.sentenceTranslation == nil && initial.isUsable)
        }
        for (word, context, expected) in [
            ("Codex", "开发者用Codex修复仓库里的代码。", "编程助手"),
            ("Codex", "開發者用Codex修復倉庫裡的代碼。", "编程助手"),
            ("Codex", "这份古代Codex是羊皮纸手抄本。", "手抄本"),
            ("Rust", "我们用Rust开发软件。", "编程语言"),
            ("Go", "Go语言支持协程。", "编程语言"),
            ("React", "我们用React编写前端组件。", "JavaScript"),
            ("Docker", "Docker容器使用镜像部署。", "容器"),
            ("PRD", "PRD记录产品需求文档。", "产品需求文档"),
            ("PRD", "广东和深圳都在PRD珠三角区域。", "珠江三角洲"),
            ("ram", "这台电脑的ram内存不足。", "随机存取"),
            ("api", "这个api接口返回数据。", "应用程序编程接口")
        ] {
            let term = try require(LocalTerminology.lookup(passage(word, context)))
            try expect(term.meaning.contains(expected))
        }
        let text = "产品团队用MVP验证需求，球队的MVP是最有价值球员。"
        try expect(LocalTerminology.lookup(passage("MVP", text))?.meaning.contains("最小可行产品") == true)
        try expect(LocalTerminology.lookup(passage("MVP", text, last: true))?.meaning.contains("最有价值球员") == true)
        try expect(LocalTerminology.lookup(passage("Codex", "我们在聊Codex。"))?.label == "多义参考")
        for (word, context, language) in [
            ("ram", "公羊ram正在山坡吃草。", "zh-Hans"), ("rest", "我需要rest休息一下。", "zh-Hans"),
            ("Rust", "铁门上的Rust是铁锈。", "zh-Hans"), ("OCR2", "这里有OCR2字符串。", "zh-Hans"),
            ("os", "os livros estão na mesa", "pt"), ("OS", "OS LIVROS ESTÃO NA MESA", "pt"),
            ("api", "Api membakar kayu itu.", "id"), ("AI", "AI CHOISI CE LIVRE", "fr")
        ] { try expect(LocalTerminology.lookup(passage(word, context, language: language)) == nil) }
        let manual = passage("OCR", "使用OCR识别图片文字。", language: "zh-Hans")
        try expect(manual.sourceLanguage == "zh-Hans" && LocalTerminology.lookup(manual)?.meaning.contains("光学字符识别") == true)
        try expect(manual.headwordLanguage == "en")
        for (word, context, expected) in [
            ("INTEGER", "已安装测试版本，INTEGER现在显示简体整数。", "整数"),
            ("LookupTranslation", "Sources/waxtranlate/LookupTranslation.swift", "名称组成词参考")
        ] {
            let sample = passage(word, context, language: "zh-Hans")
            let reference = LookupTranslation.makeResult(for: sample, meaning: word, origin: .standalone,
                                                        sentence: "Translated context.")
            if CompactGloss.mixedEnglishReference(for: sample) != nil {
                try expect(reference.origin == .dictionary && reference.meaning.contains(expected))
                print("Mixed English reference →", word, reference.meaning)
            } else {
                try expect(reference.origin == .unresolved && !reference.isUsable)
                print("No installed English/Chinese dictionary: verified unresolved boundary for", word)
            }
            try expect(reference.sentenceTranslation == "Translated context.")
        }
        try expect(CompactGloss.mixedEnglishReference(for: passage("QzxUnknown", "这里有QzxUnknown名称。")) == nil)
        let unknown = passage("UnknownSDK", "这里有UnknownSDK这个名称。")
        let unchanged = LookupTranslation.makeResult(for: unknown, meaning: "UNKNOWNsdk", origin: .standalone)
        try expect(unchanged.origin == .unresolved && !unchanged.isUsable && unchanged.meaning.isEmpty)
        let cache = LookupCache(); cache.insert(unchanged, for: unknown)
        try expect(cache.result(for: unknown) == nil)
        let region = Passage(text: "SELECT * FROM users", context: "", language: "en")
        try expect(LookupTranslation.makeResult(for: region, meaning: region.text, origin: .region).isUsable)
        let japanese = Passage(text: "猫", context: "猫が眠っています。", language: "ja")
        try expect(LookupTranslation.makeResult(for: japanese, meaning: "猫", origin: .sentence).isUsable)
        try expect(japanese.headwordLanguage == "ja")
        let stale = Passage(text: "OCR", context: "不是原词", selection: NSRange(location: 0, length: 3), language: "en")
        try expect(LocalTerminology.lookup(stale) == nil)
        let sentence = "这里用 OCR 识别图片里的文字，结果保存在本机。"
        let font = NSFont.systemFont(ofSize: 16)
        let attributes: [NSAttributedString.Key: Any] = [.font: font, .foregroundColor: NSColor.black]
        let image = NSImage(size: NSSize(width: 800, height: 90))
        image.lockFocus(); NSColor.white.setFill(); NSRect(x: 0, y: 0, width: 800, height: 90).fill()
        (sentence as NSString).draw(at: NSPoint(x: 20, y: 25), withAttributes: attributes)
        image.unlockFocus()
        let x = 20 + ("这里用 " as NSString).size(withAttributes: attributes).width + ("OCR" as NSString).size(withAttributes: attributes).width / 2
        let recognized = try Reader.recognize(image: require(image.cgImage(forProposedRect: nil, context: nil, hints: nil)),
                         target: CGPoint(x: x / 800, y: (25 + font.ascender * 0.55) / 90))
        try expect(recognized.text == "OCR" && recognized.sourceLanguage.hasPrefix("zh"))
        try expect(LocalTerminology.lookup(recognized)?.meaning.contains("光学字符识别") == true)
    }

    static func testPackedOCRAndManualLanguages() throws {
        var fonts = [NSFont.systemFont(ofSize: 20), NSFont.systemFont(ofSize: 32), NSFont.monospacedSystemFont(ofSize: 24, weight: .regular)]
        if let serif = NSFont(name: "Baskerville", size: 24) { fonts.insert(serif, at: 2) }
        else { print("Skipping Baskerville fixture: font not installed.") }
        for font in fonts {
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
