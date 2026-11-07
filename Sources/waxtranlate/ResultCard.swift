import SwiftUI
import Translation

struct ResultCard: View {
    private enum Phase { case checking, download, translating, done, unsupported, failed }

    let passage: Passage
    @ObservedObject var notebook: Notebook
    let close: () -> Void
    let speak: (String, String) -> Void
    let focusForDownload: () -> Void
    private let source: Locale.Language
    private let target: Locale.Language
    private let dictionary: [String]
    @State private var result: LookupResult?
    @State private var phase = Phase.checking
    @State private var configuration: TranslationSession.Configuration?
    @State private var copied = false

    init(passage: Passage, notebook: Notebook, close: @escaping () -> Void,
         speak: @escaping (String, String) -> Void, focusForDownload: @escaping () -> Void) {
        self.passage = passage
        self.notebook = notebook
        self.close = close
        self.speak = speak
        self.focusForDownload = focusForDownload
        let language = passage.sourceLanguage
        source = Locale.Language(identifier: language)
        target = Locale.Language(identifier: language.hasPrefix("zh") ? "en" : "zh-Hans")
        dictionary = CompactGloss.candidates(for: passage, language: language)
        _result = State(initialValue: dictionary.first.map { LookupResult(meaning: $0, origin: .dictionary) })
    }

    private var hasSentence: Bool { !passage.context.isEmpty && passage.context != passage.text }
    private var isRegion: Bool { passage.context.isEmpty }
    private var targetName: String { target.languageCode == .english ? "英语" : "简体中文" }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("\(Locale(identifier: "zh_CN").localizedString(forIdentifier: source.minimalIdentifier) ?? source.minimalIdentifier) → \(targetName)")
                    .font(.caption).foregroundStyle(DeskTheme.muted)
                Spacer()
                Button(action: close) { Image(systemName: "xmark") }
                    .buttonStyle(.plain).foregroundStyle(DeskTheme.muted).accessibilityLabel("关闭")
            }
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    if !isRegion {
                        Text(passage.text).font(.system(size: 25, weight: .semibold, design: .serif))
                    }
                    if let result {
                        HStack(alignment: .firstTextBaseline, spacing: 7) {
                            Text(result.meaning).font(isRegion ? .body : .system(size: 17, weight: .medium))
                            if result.origin == .dictionary {
                                Text("词典参考").font(.caption2).foregroundStyle(DeskTheme.muted)
                            } else if result.origin == .word && hasSentence {
                                Text("单词参考").font(.caption2).foregroundStyle(DeskTheme.muted)
                            }
                        }
                    }
                    if hasSentence || isRegion {
                        if result != nil { BookRule().padding(.vertical, 2) }
                        Text(LookupTranslation.markedSentence(passage) ?? AttributedString(isRegion ? passage.text : passage.context))
                            .font(.system(.callout, design: .serif)).foregroundStyle(DeskTheme.muted)
                        if let translation = result?.sentenceTranslation {
                            Text(translation).font(.callout)
                        }
                    }
                    translationStatus
                }.frame(maxWidth: .infinity, alignment: .leading).textSelection(.enabled)
            }
            BookRule()
            HStack(spacing: 12) {
                Button { speak(passage.text, source.minimalIdentifier) } label: { Image(systemName: "speaker.wave.2") }
                    .accessibilityLabel("朗读").help("朗读原文")
                Button {
                    guard let result else { return }
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(result.meaning, forType: .string)
                    copied = true
                } label: { Image(systemName: copied ? "checkmark" : "doc.on.doc") }
                    .disabled(result == nil).accessibilityLabel("复制译文").help("复制译文")
                Spacer()
                Button {
                    guard let result else { return }
                    notebook.save(passage, translation: result.meaning, sentenceTranslation: result.sentenceTranslation)
                } label: {
                    Label(notebook.contains(passage) ? "已加入生词本" : "加入生词本",
                          systemImage: notebook.contains(passage) ? "bookmark.fill" : "bookmark")
                }.disabled(result == nil || notebook.contains(passage) || phase == .translating)
            }.buttonStyle(.plain).controlSize(.small).foregroundStyle(DeskTheme.muted)
        }
        .padding(16).frame(width: 390, height: isRegion ? 276 : 246)
        .foregroundStyle(DeskTheme.ink).tint(DeskTheme.wax).background(DeskTheme.sheet)
        .overlay(alignment: .top) { Rectangle().fill(DeskTheme.binding).frame(height: 3) }
        .task {
            let availability = await LanguageAvailability().status(from: source, to: target)
            guard !Task.isCancelled else { return }
            switch availability {
            case .installed: start()
            case .supported: phase = .download
            default: phase = .unsupported
            }
        }
        .translationTask(configuration) { session in
            do {
                try await session.prepareTranslation()
                let translated = try await LookupTranslation.translate(passage, session: session, dictionary: dictionary)
                try Task.checkCancellation()
                result = translated
                copied = false
                phase = .done
            } catch {
                if !Task.isCancelled { phase = .failed }
            }
        }
    }

    @ViewBuilder private var translationStatus: some View {
        switch phase {
        case .translating:
            ProgressView(hasSentence ? "正在翻译原句…" : "正在翻译…").controlSize(.small)
        case .download:
            Button(hasSentence ? "下载语言包以翻译原句…" : "下载翻译语言包…") {
                focusForDownload()
                start()
            }.controlSize(.small)
        case .failed:
            Button("系统翻译未完成 · 重试") { focusForDownload(); start() }.controlSize(.small)
        case .unsupported:
            Text("系统翻译暂不支持这个语言组合。").font(.caption).foregroundStyle(DeskTheme.muted)
        case .checking, .done:
            EmptyView()
        }
    }

    private func start() {
        phase = .translating
        if configuration != nil {
            configuration?.invalidate()
        } else {
            configuration = TranslationSession.Configuration(source: source, target: target)
        }
    }
}
