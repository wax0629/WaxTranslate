import SwiftUI
import Translation
import NaturalLanguage

struct TranslationRequest: Identifiable, Equatable {
    let id = UUID()
    let text: String
    let source: String
    var target: String { source.hasPrefix("zh") ? "en" : "zh-Hans" }
}

@MainActor final class ReadingDocument: ObservableObject {
    @Published var text = "" { didSet { if oldValue != text { cancel() } } }
    @Published private(set) var translation = ""
    @Published private(set) var status = "粘贴文章，双击一个词即可按原句查词。"
    @Published private(set) var request: TranslationRequest?
    @Published private(set) var busy = false
    @Published private(set) var translationLanguage = "zh-Hans"

    func begin(language: String) {
        let input = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !input.isEmpty else { status = "先输入或粘贴需要翻译的文字。"; return }
        guard input.count <= 20000 else { status = "这段文字较长，请分成不超过 20,000 字的段落。"; return }
        request = TranslationRequest(text: input, source: language.isEmpty ? LanguageResolver.resolve(input) : language)
        translationLanguage = request?.target ?? "zh-Hans"
        translation = ""
        busy = true
        status = "正在翻译…首次使用时可按系统提示下载语言包。"
    }

    func cancel() {
        request = nil
        busy = false
        translation = ""
        status = "双击原文查词，或翻译整段文字。"
    }

    func complete(_ request: TranslationRequest, result: Result<String, Error>) {
        guard self.request?.id == request.id else { return }
        busy = false
        self.request = nil
        switch result {
        case .success(let output): translation = TranslationOutput.normalize(output, target: request.target); status = "译文已更新 · Apple 本机翻译"
        case .failure: status = "翻译未完成。请检查语言包后重试，也可在设置中选择源语言。"
        }
    }
}

// One mounted runner per request. Its immutable input and ID prevent a late
// completion from a replaced session from overwriting an edited document.
struct TranslationRunner: View {
    let request: TranslationRequest
    let completion: (TranslationRequest, Result<String, Error>) -> Void
    @State private var configuration: TranslationSession.Configuration?

    var body: some View {
        Color.clear.frame(width: 0, height: 0)
            .onAppear {
                configuration = TranslationSession.Configuration(source: Locale.Language(identifier: request.source),
                                                                  target: Locale.Language(identifier: request.target))
            }
            .translationTask(configuration) { session in
                do {
                    try await session.prepareTranslation()
                    let response = try await session.translate(request.text)
                    try Task.checkCancellation()
                    completion(request, .success(response.targetText))
                } catch { if !Task.isCancelled { completion(request, .failure(error)) } }
            }
    }
}

struct ReadingPage: View {
    @ObservedObject var document: ReadingDocument
    @ObservedObject var preferences: Preferences
    let lookup: (Passage) -> Void
    let speak: (String, String) -> Void
    @State private var copied = false

    var body: some View {
        GeometryReader { viewport in
          ScrollView {
            VStack(alignment: .leading, spacing: 18) {
            HStack(alignment: .firstTextBaseline) {
                Text("对照翻译").font(.system(size: 27, weight: .semibold))
                Spacer()
                Picker("源语言", selection: $preferences.language) {
                    ForEach(ReadingLanguage.allCases) { Text($0.title).tag($0) }
                }.labelsHidden().frame(width: 120).accessibilityLabel("阅读源语言")
            }
            HStack(spacing: 10) {
                Button("粘贴") {
                    if let text = NSPasteboard.general.string(forType: .string) { document.text = text }
                }
                Button("试读样文") {
                    document.text = "These results do not rule out infection.\nThe device ran out of memory before the test ended.\nThey sat on the river bank and watched the water."
                }
                Spacer()
                if document.busy { Button("取消") { document.cancel() } }
                Button(document.busy ? "正在翻译…" : "翻译全文") { document.begin(language: preferences.language.rawValue) }
                    .buttonStyle(ReaderActionStyle(emphasized: true)).disabled(document.busy || document.text.isEmpty)
                    .keyboardShortcut(.return, modifiers: .command)
            }.buttonStyle(ReaderActionStyle())
            GeometryReader { geometry in
                if geometry.size.width >= 650 {
                    HStack(alignment: .top, spacing: 0) {
                        sourceColumn
                        Rectangle().fill(DeskTheme.rule).frame(width: 1).padding(.horizontal, 22)
                        targetColumn
                    }
                } else {
                    VStack(spacing: 16) { sourceColumn; BookRule(); targetColumn }
                }
            }.frame(height: viewport.size.width - 56 >= 650 ? max(240, viewport.size.height - 200) : 480)
            Text(document.status).font(.system(size: 12)).foregroundStyle(DeskTheme.muted)
                .fixedSize(horizontal: false, vertical: true).accessibilityIdentifier("reading.status")
            }.padding(28)
          }
        }
        .background(alignment: .bottomLeading) {
            if let request = document.request {
                TranslationRunner(request: request, completion: document.complete).id(request.id)
            }
        }
        .onChange(of: preferences.language) { _, _ in document.cancel() }
        .onChange(of: document.translation) { _, _ in copied = false }
    }

    private var sourceColumn: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("原文").font(.system(size: 14, weight: .semibold))
                Spacer()
                Button { speak(document.text, preferences.language == .auto ? LanguageResolver.resolve(document.text) : preferences.language.rawValue) } label: {
                    Image(systemName: "speaker.wave.2")
                }.buttonStyle(.plain).disabled(document.text.isEmpty).help("朗读原文").accessibilityLabel("朗读原文")
            }
            ReadingEditor(text: $document.text, language: preferences.language.rawValue, lookup: lookup)
                .background(DeskTheme.sheet)
                .overlay(alignment: .topLeading) {
                    if document.text.isEmpty {
                        Text("在这里粘贴或输入外文…").foregroundStyle(DeskTheme.muted).padding(9).allowsHitTesting(false)
                    }
                }
        }.frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var targetColumn: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("译文").font(.system(size: 14, weight: .semibold))
                Spacer()
                Button { speak(document.translation, document.translationLanguage) } label: {
                    Image(systemName: "speaker.wave.2")
                }.disabled(document.translation.isEmpty).help("朗读译文").accessibilityLabel("朗读译文")
                Button {
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(document.translation, forType: .string)
                    copied = true
                } label: { Image(systemName: copied ? "checkmark" : "doc.on.doc") }
                    .disabled(document.translation.isEmpty).help("复制译文").accessibilityLabel("复制全文译文")
            }.buttonStyle(.plain)
            ScrollView {
                Text(document.translation.isEmpty ? "整段译文显示在这里。\n查一个词时，双击左侧原文。" : document.translation)
                    .font(.system(size: 17)).lineSpacing(7).foregroundStyle(document.translation.isEmpty ? DeskTheme.muted : DeskTheme.ink)
                    .frame(maxWidth: .infinity, alignment: .leading).padding(9).textSelection(.enabled)
            }.frame(maxWidth: .infinity, maxHeight: .infinity)
        }.frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

private final class LookupTextView: NSTextView {
    var lookup: ((NSRange) -> Void)?
    override func mouseDown(with event: NSEvent) {
        super.mouseDown(with: event)
        if event.clickCount == 2, selectedRange().length > 0 { lookup?(selectedRange()) }
    }
}

struct ReadingEditor: NSViewRepresentable {
    @Binding var text: String
    let language: String
    let lookup: (Passage) -> Void

    func makeCoordinator() -> Coordinator { Coordinator(self) }
    func makeNSView(context: Context) -> NSScrollView {
        let scroll = NSScrollView()
        let editor = LookupTextView()
        editor.isRichText = false
        editor.isAutomaticQuoteSubstitutionEnabled = false
        editor.font = NSFont(name: "Baskerville", size: 20) ?? .systemFont(ofSize: 18)
        editor.textContainerInset = NSSize(width: 9, height: 9)
        editor.isVerticallyResizable = true
        editor.isHorizontallyResizable = false
        editor.autoresizingMask = [.width]
        editor.textContainer?.widthTracksTextView = true
        editor.delegate = context.coordinator
        editor.setAccessibilityLabel("阅读原文")
        editor.lookup = { [weak coordinator = context.coordinator] range in coordinator?.lookup(range) }
        scroll.documentView = editor
        scroll.hasVerticalScroller = true
        return scroll
    }
    func updateNSView(_ scroll: NSScrollView, context: Context) {
        context.coordinator.parent = self
        guard let editor = scroll.documentView as? LookupTextView else { return }
        if editor.string != text { editor.string = text }
        editor.backgroundColor = NSColor(DeskTheme.sheet)
        editor.textColor = NSColor(DeskTheme.ink)
    }
    final class Coordinator: NSObject, NSTextViewDelegate {
        var parent: ReadingEditor
        init(_ parent: ReadingEditor) { self.parent = parent }
        func textDidChange(_ notification: Notification) {
            if let editor = notification.object as? NSTextView { parent.text = editor.string }
        }
        func lookup(_ range: NSRange) {
            let line = TextLine(text: parent.text, frame: CGRect(x: 0, y: 0, width: 1, height: 1), hit: range)
            if let passage = try? SentenceContext.passage(in: [line], language: parent.language.isEmpty ? nil : parent.language) {
                parent.lookup(passage)
            }
        }
    }
}
