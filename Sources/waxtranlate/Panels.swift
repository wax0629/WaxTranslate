import SwiftUI

let accent = Color(red: 0.14, green: 0.52, blue: 0.42)

private enum Page: String, CaseIterable, Identifiable {
    case start = "取词", words = "生词本", review = "复习"
    var id: Self { self }
    var icon: String {
        switch self { case .start: return "cursorarrow.rays"; case .words: return "bookmark"; case .review: return "rectangle.on.rectangle" }
    }
}

struct LibraryView: View {
    @ObservedObject var notebook: Notebook
    let shortcutErrors: [String]
    let demo: () -> Void
    let region: () -> Void
    let permission: () -> Void
    @State private var page = Page.start
    @State private var query = ""
    @State private var revealed: UUID?
    @State private var captureAllowed = false

    var body: some View {
        HStack(spacing: 0) {
            VStack(alignment: .leading, spacing: 6) {
                Label("我靠翻译", systemImage: "character.book.closed.fill")
                    .font(.system(size: 17, weight: .semibold)).lineLimit(1).foregroundStyle(accent).padding(.bottom, 24)
                ForEach(Page.allCases) { p in
                    Button { page = p } label: {
                        Label(p.rawValue, systemImage: p.icon).frame(maxWidth: .infinity, alignment: .leading)
                            .padding(9).background(page == p ? accent.opacity(0.14) : .clear, in: RoundedRectangle(cornerRadius: 7))
                    }.buttonStyle(.plain)
                }
                Spacer()
            }.padding(16).frame(width: 165).background(.quaternary.opacity(0.4))
            Divider()
            VStack(alignment: .leading, spacing: 18) {
                Text(page.rawValue).font(.system(size: 28, weight: .semibold, design: .serif))
                switch page {
                case .start:
                    Text("在其他应用中指向文字，按快捷键查看译文。").foregroundStyle(.secondary)
                    shortcut("悬停取词", "⌥ ⇧ T", "将光标停在一个词上")
                    shortcut("区域翻译", "⌥ ⇧ R", "拖动框选文字，按 Esc 取消")
                    if !shortcutErrors.isEmpty {
                        Text("快捷键已被占用：" + shortcutErrors.joined(separator: "、")).foregroundStyle(.orange)
                    }
                    HStack { Button("试译示例", action: demo); Button("框选屏幕", action: region) }
                    Spacer()
                    HStack {
                        Label(captureAllowed ? "屏幕取词已授权" : "屏幕取词待授权",
                              systemImage: captureAllowed ? "checkmark.circle" : "lock")
                            .font(.caption).foregroundStyle(.secondary)
                        Button("设置屏幕录制权限…", action: permission).controlSize(.small)
                    }
                case .words:
                    TextField("搜索原文或译文", text: $query).textFieldStyle(.roundedBorder)
                    let items = notebook.entries.filter { query.isEmpty || $0.source.localizedCaseInsensitiveContains(query) || $0.target.localizedCaseInsensitiveContains(query) }
                    if items.isEmpty {
                        Text(query.isEmpty ? "在翻译浮窗中点击「加入生词本」，即可在这里复习。" : "没有匹配的词条。").foregroundStyle(.secondary)
                    }
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 12) {
                            ForEach(items) { item in
                                HStack(alignment: .top) {
                                    VStack(alignment: .leading, spacing: 5) {
                                        Text(item.source).font(.headline)
                                        Text(item.displayMeaning)
                                        if !item.context.isEmpty { Text(item.context).font(.caption).foregroundStyle(.secondary) }
                                        if let sentence = item.sentenceTranslation { Text(sentence).font(.caption) }
                                    }.textSelection(.enabled)
                                    Spacer()
                                    Button { notebook.remove(item.id) } label: { Image(systemName: "trash") }.accessibilityLabel("删除词条")
                                }; Divider()
                            }
                        }
                    }
                case .review:
                    TimelineView(.periodic(from: .now, by: 30)) { time in
                        if let item = notebook.entries.filter({ $0.due <= time.date }).min(by: { $0.due < $1.due }) {
                            VStack(alignment: .leading, spacing: 16) {
                                Text(item.source).font(.title)
                                Text(item.context).foregroundStyle(.secondary)
                                if revealed == item.id {
                                    Text(item.displayMeaning).font(.title3)
                                    if let sentence = item.sentenceTranslation { Text(sentence).font(.callout) }
                                    HStack {
                                        Button("再学一次") { notebook.review(item.id, remembered: false); revealed = nil }
                                        Button("记住了") { notebook.review(item.id, remembered: true); revealed = nil }
                                    }
                                } else { Button("显示释义") { revealed = item.id } }
                            }
                        } else { Text("当前没有待复习的词条。").foregroundStyle(.secondary) }
                    }
                    Spacer()
                }
            }.padding(26).frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }.frame(minWidth: 590, minHeight: 380).tint(accent)
        .onAppear { captureAllowed = CGPreflightScreenCaptureAccess() }
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
            captureAllowed = CGPreflightScreenCaptureAccess()
        }
    }

    private func shortcut(_ title: String, _ keys: String, _ hint: String) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) { Text(title).font(.headline); Text(hint).font(.caption).foregroundStyle(.secondary) }
            Spacer()
            Text(keys).font(.system(.body, design: .monospaced)).padding(6).background(.quaternary, in: RoundedRectangle(cornerRadius: 5))
        }
    }
}
