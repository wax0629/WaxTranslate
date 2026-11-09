import SwiftUI
import Translation

struct ResultCard: View {
    private enum Phase { case checking, download, translating, done, unsupported, failed }
    let passage: Passage
    @ObservedObject var notebook: Notebook
    @ObservedObject var preferences: Preferences
    let trace: LookupTrace
    let close: () -> Void
    let speak: (String, String) -> Void
    let focusForDownload: () -> Void
    let pin: (Bool) -> Void
    let resize: (CGSize) -> Void
    private let source: Locale.Language
    private let target: Locale.Language
    private let dictionary: [String]
    private let term: TermMeaning?
    private let cacheHit: Bool
    private let policy: LookupPolicy
    private let excerpt: SentenceExcerpt
    @State private var result: LookupResult?
    @State private var phase = Phase.checking
    @State private var configuration: TranslationSession.Configuration?
    @State private var copied = false
    @State private var pinned = false
    @State private var expanded = false
    @State private var contextVisible = false
    @State private var contextRequested = false
    @State private var secondaryVisible = false
    @State private var recordID: UUID?
    @State private var references: [WordReference] = []
    @State private var referenceStatus = ""
    @State private var referenceBusy = false
    @State private var referenceAttempt = 0

    init(passage: Passage, notebook: Notebook, preferences: Preferences, trace: LookupTrace = LookupTrace(), close: @escaping () -> Void,
         speak: @escaping (String, String) -> Void, focusForDownload: @escaping () -> Void,
         pin: @escaping (Bool) -> Void = { _ in }, resize: @escaping (CGSize) -> Void = { _ in }) {
        self.passage = passage
        self.notebook = notebook
        self.preferences = preferences
        self.trace = trace
        self.close = close
        self.speak = speak
        self.focusForDownload = focusForDownload
        self.pin = pin
        self.resize = resize
        policy = LookupPolicy(passage)
        _contextVisible = State(initialValue: LookupPolicy(passage).defaultsToContext)
        excerpt = SentenceExcerpt(passage)
        let languageBegan = LookupTrace.now
        let language = passage.sourceLanguage
        trace.record("lookup.language", since: languageBegan)
        source = Locale.Language(identifier: language)
        target = Locale.Language(identifier: language.hasPrefix("zh") ? "en" : "zh-Hans")
        let began = LookupTrace.now
        let decision = LookupPolicy(passage)
        dictionary = decision.needsConfirmation ? [] : CompactGloss.candidates(for: passage, language: language)
            + (CompactGloss.mixedEnglishReference(for: passage).flatMap { $0.hasPrefix("名称组成词参考") ? nil : [$0] } ?? [])
        term = decision.term
        trace.record("lookup.dictionary_and_terms", since: began)
        let cached = decision.object == .word || decision.object == .region ? LookupCache.shared.result(for: passage) : nil
        cacheHit = cached != nil
        _phase = State(initialValue: cached == nil && term == nil ? .checking : .done)
        _result = State(initialValue: decision.needsConfirmation ? LookupResult(meaning: "", origin: .unresolved) : LookupResult.initial(term: term, cached: cached, dictionary: dictionary))
    }

    private var hasSentence: Bool { !passage.context.isEmpty && passage.context != passage.text }
    private var isRegion: Bool { passage.context.isEmpty }
    private var sourceName: String { Locale(identifier: "zh_CN").localizedString(forIdentifier: source.minimalIdentifier) ?? source.minimalIdentifier }
    private var referenceAvailable: Bool { !isRegion && !passage.isPhrase && WordReferences.request(for: passage.text) != nil }

    var body: some View {
        VStack(alignment: .leading, spacing: 13) {
            header
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    if let result {
                        Text(result.isUsable ? result.meaning : policy.unresolvedMessage)
                            .font(isRegion || !result.isUsable ? .system(size: 16) : .system(size: 17, weight: .medium))
                            .fixedSize(horizontal: false, vertical: true)
                        originLabel(result)
                    }
                    translationStatus
                    queryExtras
                    if !references.isEmpty {
                        BookRule()
                        Text(references.count > 1 ? "Wikidata · 同名参考" : "Wikidata · 百科参考")
                            .font(.caption).foregroundStyle(DeskTheme.muted)
                        ForEach(references) { reference in
                            Link(destination: reference.url) {
                                HStack(alignment: .top) { Text(reference.description); Image(systemName: "arrow.up.right") }
                            }.font(.callout)
                        }
                    }
                    if !referenceStatus.isEmpty { Text(referenceStatus).font(.caption).foregroundStyle(DeskTheme.muted) }
                    if let error = notebook.error { Text(error).font(.caption).foregroundStyle(DeskTheme.accent) }
                }.frame(maxWidth: .infinity, alignment: .leading).textSelection(.enabled)
            }.frame(maxHeight: expanded ? 360 : hasSentence ? 270 : isRegion ? 260 : term != nil ? 180 : 110)
            footer
        }
        .padding(19).frame(width: 365)
        .fixedSize(horizontal: false, vertical: true)
        .foregroundStyle(DeskTheme.ink).tint(DeskTheme.accent).background(DeskTheme.sheet)
        .background(GeometryReader { geometry in Color.clear.preference(key: CardSizeKey.self, value: geometry.size) })
        .onPreferenceChange(CardSizeKey.self, perform: resize)
        .task {
            let began = LookupTrace.now
            if let result { record(result); trace.record("lookup.first_reference", since: began) }
            if policy.needsConfirmation { phase = .done; return }
            if !policy.automaticallyTranslatesContext {
                if result == nil { result = LookupResult(meaning: "", origin: .unresolved) }
                phase = .done
                // A mixed-language word needs an independent English reference,
                // never a Chinese→English sentence call to explain its headword.
                return
            }
            if cacheHit { trace.record("lookup.cache_hit", since: began); return }
            await prepare()
        }
        .translationTask(configuration) { session in
            do {
                let requestedContext = contextRequested
                let requestedExpanded = expanded
                let requestedPassage = displayedPassage
                let began = LookupTrace.now
                try await session.prepareTranslation()
                trace.record("translation.prepare", since: began)
                let translated: LookupResult
                if requestedContext {
                    var preserved = result ?? LookupResult(meaning: "", origin: .unresolved)
                    let text = try await session.translate(requestedPassage.context).targetText
                    if !requestedExpanded && excerpt.isTruncated { preserved.excerptTranslation = TranslationOutput.normalize(text, target: target.minimalIdentifier) }
                    else { preserved.sentenceTranslation = TranslationOutput.normalize(text, target: target.minimalIdentifier) }
                    translated = preserved
                } else {
                    translated = try await LookupTranslation.translate(passage, session: session, dictionary: dictionary, trace: trace)
                }
                try Task.checkCancellation()
                guard !requestedContext || (contextRequested && expanded == requestedExpanded) else { phase = .done; return }
                let displayed = translated
                result = displayed
                if !requestedContext { LookupCache.shared.insert(displayed, for: passage) }
                copied = false
                phase = .done
                record(displayed)
                trace.record("lookup.complete", since: began)
            } catch {
                if !Task.isCancelled { phase = .failed }
            }
        }
        .task(id: referenceAttempt) {
            guard referenceAvailable, referenceAttempt > 0 else { return }
            referenceBusy = true
            defer { referenceBusy = false }
            do {
                let found = try await WordReferences.search(passage.text)
                try Task.checkCancellation()
                references = found
                referenceStatus = found.isEmpty ? "没有找到精确同名的百科参考。" : ""
            } catch { if !Task.isCancelled { referenceStatus = "百科参考暂不可用，可重试。" } }
        }
    }

    @ViewBuilder private var queryExtras: some View {
                    if policy.needsConfirmation {
                        Button(secondaryVisible ? "收起参考" : policy.object == .code ? "查看组成词" : "查看候选解释") { secondaryVisible.toggle() }
                            .buttonStyle(.plain).font(.caption).foregroundStyle(DeskTheme.muted)
                        if secondaryVisible {
                            Text(policy.object == .uncertainName ? "Apple VoiceOver：屏幕朗读辅助功能。普通词 voice-over：画外音、旁白。需要更多上下文确认当前所指。" : CompactGloss.mixedEnglishReference(for: passage) ?? "暂没有足够的组成词资料；不能据拼写推断代码功能。")
                                .font(.system(size: 12)).foregroundStyle(DeskTheme.muted)
                        }
                    }
                    if hasSentence || isRegion {
                        if contextVisible || isRegion { contextContent }
                        else { Button("查看相关原文") { contextVisible = true }.buttonStyle(.plain).font(.caption).foregroundStyle(DeskTheme.muted) }
                    }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline, spacing: 12) {
                Text(isRegion ? "框选翻译" : passage.text).font(isRegion ? .headline : .custom("Baskerville", size: 27))
                    .lineLimit(2).textSelection(.enabled)
                if !isRegion {
                    Button { speak(passage.text, policy.headwordLanguage) } label: { Image(systemName: "speaker.wave.2") }
                        .help("朗读词语").accessibilityLabel("朗读词语")
                }
                Spacer(minLength: 0)
                Button { pinned.toggle(); pin(pinned) } label: { Image(systemName: pinned ? "pin.fill" : "pin") }
                    .help(pinned ? "取消固定" : "固定浮窗").accessibilityLabel(pinned ? "取消固定" : "固定浮窗")
                Button(action: close) { Image(systemName: "xmark") }
                    .help("关闭").accessibilityLabel("关闭取词卡").keyboardShortcut(.cancelAction)
            }.buttonStyle(.plain)
            Text(policy.caption)
                .font(.system(size: 11)).foregroundStyle(DeskTheme.muted)
        }
    }

    @ViewBuilder private func originLabel(_ result: LookupResult) -> some View {
        if result.origin == .term, let term {
            Text(term.label + " · " + term.kind).font(.caption).foregroundStyle(DeskTheme.muted)
        } else if result.origin == .dictionary {
            Text("常见词义参考").font(.caption).foregroundStyle(DeskTheme.muted)
        } else if result.origin == .standalone && hasSentence {
            Text(passage.isPhrase ? "短语参考" : "单词参考").font(.caption).foregroundStyle(DeskTheme.muted)
        }
    }

    private var contextContent: some View {
        VStack(alignment: .leading, spacing: 10) {
            BookRule()
            HStack {
                Text(isRegion ? "原文" : !expanded && excerpt.isTruncated ? "相关原文节选" : "相关原文").font(.caption).foregroundStyle(DeskTheme.muted)
                Spacer()
                Button { speak(isRegion ? passage.text : displayedPassage.context, source.minimalIdentifier) } label: { Image(systemName: "speaker.wave.2") }
                    .buttonStyle(.plain).help("朗读原句").accessibilityLabel("朗读原句")
            }
            Text(LookupTranslation.markedSentence(displayedPassage) ?? AttributedString(isRegion ? passage.text : displayedPassage.context))
                .font(.custom("Baskerville", size: 16)).lineSpacing(3)
            if (policy.automaticallyTranslatesContext || contextRequested), let translated = displayedSentenceTranslation { Text(translated).font(.system(size: 13)).lineSpacing(3) }
            else if expanded && result?.excerptTranslation != nil {
                Text("完整句译暂不可用，可收起查看节选对照。").font(.caption).foregroundStyle(DeskTheme.muted)
            }
            HStack(spacing: 18) {
                if hasSentence && excerpt.isTruncated {
                    Button(expanded ? "收起" : "展开当前句") {
                        expanded.toggle()
                        if contextRequested { contextRequested = false; phase = .done; configuration = nil }
                    }
                }
                if !policy.automaticallyTranslatesContext {
                    Button(contextRequested && displayedSentenceTranslation != nil ? "收起句译" : "翻译这句") {
                        if contextRequested && displayedSentenceTranslation != nil { contextRequested = false; configuration = nil; phase = .done }
                        else { contextRequested = true; Task { await prepare() } }
                    }
                    if !policy.defaultsToContext { Button("收起原文") { contextVisible = false } }
                }
            }.buttonStyle(.plain).font(.caption).foregroundStyle(DeskTheme.muted)
        }
    }

    private var displayedPassage: Passage { expanded ? passage : excerpt.passage }
    private var displayedSentenceTranslation: String? {
        !expanded && excerpt.isTruncated ? result?.excerptTranslation : result?.sentenceTranslation
    }

    private var footer: some View {
        HStack(spacing: 14) {
            Button {
                guard let result, result.isUsable else { return }
                notebook.save(passage, translation: result.meaning, sentenceTranslation: result.sentenceTranslation)
            } label: {
                Label(notebook.contains(passage) ? "已加入生词本" : "加入生词本", systemImage: notebook.contains(passage) ? "bookmark.fill" : "bookmark")
            }.disabled(result?.isUsable != true || notebook.contains(passage) || (phase == .translating && term == nil))
            Spacer()
            Button {
                guard let result, result.isUsable else { return }
                NSPasteboard.general.clearContents(); NSPasteboard.general.setString(result.meaning, forType: .string); copied = true
            } label: { Image(systemName: copied ? "checkmark" : "doc.on.doc") }
                .disabled(result?.isUsable != true).help("复制释义").accessibilityLabel("复制释义")
            if referenceAvailable {
                Button { referenceAttempt += 1 } label: { Image(systemName: "globe") }
                    .disabled(referenceBusy).help("查询百科参考，仅发送当前词语").accessibilityLabel("查询百科参考")
            }
        }.buttonStyle(.plain).font(.system(size: 12)).foregroundStyle(DeskTheme.accent)
    }

    @ViewBuilder private var translationStatus: some View {
        switch phase {
        case .checking: ProgressView("检查本机语言包…").controlSize(.small)
        case .translating: ProgressView(hasSentence ? "正在翻译原句…" : "正在翻译…").controlSize(.small)
        case .download:
            Button("下载\(sourceName)翻译语言包…") { focusForDownload(); start() }.controlSize(.small)
        case .failed:
            Button("系统翻译未完成 · 重试") { focusForDownload(); start() }.controlSize(.small)
        case .unsupported:
            Text("系统不支持这个语言组合，可在设置中选择源语言后重试。").font(.caption).foregroundStyle(DeskTheme.muted)
        case .done:
            if result?.origin == .unresolved && !policy.needsConfirmation { Text("可更换语境或查看参考来源。").font(.caption).foregroundStyle(DeskTheme.muted) }
        }
    }

    private func record(_ result: LookupResult) {
        guard result.isUsable else { return }
        if let recordID { notebook.updateLookup(recordID, meaning: result.meaning) }
        else { recordID = notebook.recordLookup(passage, meaning: result.meaning) }
    }
    private func prepare() async {
        let began = LookupTrace.now
        let availability = await LanguageAvailability().status(from: source, to: target)
        trace.record("translation.availability", since: began)
        guard !Task.isCancelled else { return }
        switch availability {
        case .installed: start()
        case .supported: phase = .download
        default: phase = .unsupported
        }
    }
    private func start() {
        phase = .translating
        if configuration != nil { configuration?.invalidate() }
        else { configuration = TranslationSession.Configuration(source: source, target: target) }
    }
}

private struct CardSizeKey: PreferenceKey {
    static var defaultValue = CGSize.zero
    static func reduce(value: inout CGSize, nextValue: () -> CGSize) { value = nextValue() }
}
