import SwiftUI

private enum Page: String, CaseIterable, Identifiable {
    case start = "取词", words = "生词本", review = "复习"
    var id: Self { self }
    var icon: String {
        switch self {
        case .start: return "cursorarrow.rays"
        case .words: return "bookmark"
        case .review: return "rectangle.on.rectangle"
        }
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
            VStack(alignment: .leading, spacing: 7) {
                Label("我靠翻译", systemImage: "character.book.closed.fill")
                    .font(.system(size: 18, weight: .semibold, design: .serif))
                    .foregroundStyle(DeskTheme.ivory).padding(.vertical, 8)
                Rectangle().fill(DeskTheme.gilt.opacity(0.6)).frame(height: 1).padding(.bottom, 12)
                ForEach(Page.allCases) { p in
                    Button { page = p } label: {
                        Label(p.rawValue, systemImage: p.icon)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.horizontal, 12).padding(.vertical, 9)
                            .background(page == p ? DeskTheme.binding : .clear, in: RoundedRectangle(cornerRadius: 3))
                            .overlay(alignment: .leading) {
                                if page == p { Rectangle().fill(DeskTheme.gilt).frame(width: 2) }
                            }
                            .contentShape(Rectangle())
                    }.buttonStyle(.plain).foregroundStyle(DeskTheme.ivory)
                        .accessibilityAddTraits(page == p ? .isSelected : [])
                }
                Spacer()
            }.padding(14).frame(width: 150).background(WalnutGrain())
            Rectangle().fill(DeskTheme.rule).frame(width: 2)
            VStack(alignment: .leading, spacing: 14) {
                HStack(spacing: 14) {
                    Text(page.rawValue).font(.system(size: 27, weight: .semibold, design: .serif))
                    BookRule()
                }
                switch page {
                case .start: startPage
                case .words: wordList
                case .review: reviewPage
                }
            }.padding(22).frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                .foregroundStyle(DeskTheme.ink).background(DeskTheme.paper)
        }.frame(minWidth: 590, minHeight: 380).tint(DeskTheme.wax)
        .onAppear { captureAllowed = CGPreflightScreenCaptureAccess() }
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
            captureAllowed = CGPreflightScreenCaptureAccess()
        }
    }

    private var startPage: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 15) {
                Text("在其他应用中指向文字，按快捷键查看译文。").foregroundStyle(DeskTheme.muted)
                VStack(alignment: .leading, spacing: 12) {
                    shortcut("悬停取词", "⌥ ⇧ T", "将光标停在一个词上")
                    BookRule()
                    shortcut("区域翻译", "⌥ ⇧ R", "拖动框选文字，按 Esc 取消")
                }.padding(16).background(DeskTheme.sheet)
                    .overlay { Rectangle().strokeBorder(DeskTheme.rule, lineWidth: 1) }
                if !shortcutErrors.isEmpty {
                    Text("快捷键已被占用：" + shortcutErrors.joined(separator: "、")).foregroundStyle(DeskTheme.wax)
                }
                HStack {
                    Button("试译示例", action: demo).buttonStyle(.borderedProminent).tint(DeskTheme.binding)
                    Button("框选屏幕", action: region)
                }
                HStack {
                    Label(captureAllowed ? "屏幕取词已授权" : "屏幕取词待授权",
                          systemImage: captureAllowed ? "checkmark.circle" : "lock")
                        .font(.caption).foregroundStyle(DeskTheme.muted)
                    Button("设置屏幕录制权限…", action: permission).controlSize(.small)
                }
            }.frame(maxWidth: .infinity, alignment: .leading).padding(2)
        }
    }

    private func shortcut(_ title: String, _ keys: String, _ hint: String) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text(title).font(.system(size: 17, weight: .semibold, design: .serif))
                Text(hint).font(.caption).foregroundStyle(DeskTheme.muted)
            }
            Spacer()
            Text(keys).font(.system(.body, design: .monospaced))
                .padding(.horizontal, 9).padding(.vertical, 5)
                .foregroundStyle(DeskTheme.wax).background(DeskTheme.paper)
                .overlay { RoundedRectangle(cornerRadius: 3).strokeBorder(DeskTheme.rule, lineWidth: 1) }
        }
    }

    @ViewBuilder private var wordList: some View {
        TextField("搜索原文或译文", text: $query).textFieldStyle(.roundedBorder)
        let items = notebook.entries.filter {
            query.isEmpty || $0.source.localizedCaseInsensitiveContains(query) || $0.target.localizedCaseInsensitiveContains(query)
        }
        if items.isEmpty {
            Text(query.isEmpty ? "在翻译浮窗中点击「加入生词本」，即可在这里复习。" : "没有匹配的词条。")
                .foregroundStyle(DeskTheme.muted)
        } else {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 12) {
                    ForEach(items) { item in
                        HStack(alignment: .top) {
                            VStack(alignment: .leading, spacing: 5) {
                                Text(item.source).font(.system(size: 20, weight: .semibold, design: .serif))
                                Text(item.displayMeaning)
                                if !item.context.isEmpty { Text(item.context).font(.callout).foregroundStyle(DeskTheme.muted) }
                                if let sentence = item.sentenceTranslation { Text(sentence).font(.callout) }
                            }.textSelection(.enabled)
                            Spacer()
                            Button { notebook.remove(item.id) } label: { Image(systemName: "trash") }
                                .accessibilityLabel("删除词条")
                        }
                        BookRule()
                    }
                }.padding(14)
            }.background(DeskTheme.sheet)
        }
    }

    private var reviewPage: some View {
        TimelineView(.periodic(from: .now, by: 30)) { time in
            if let item = notebook.entries.filter({ $0.due <= time.date }).min(by: { $0.due < $1.due }) {
                ScrollView {
                    VStack(alignment: .leading, spacing: 14) {
                        Text(item.source).font(.system(size: 25, weight: .semibold, design: .serif))
                        Text(item.context).foregroundStyle(DeskTheme.muted)
                        BookRule()
                        if revealed == item.id {
                            Text(item.displayMeaning).font(.title3)
                            if let sentence = item.sentenceTranslation { Text(sentence).font(.callout) }
                            HStack {
                                Button("再学一次") { notebook.review(item.id, remembered: false); revealed = nil }
                                Button("记住了") { notebook.review(item.id, remembered: true); revealed = nil }
                            }
                        } else { Button("显示释义") { revealed = item.id } }
                    }.padding(16).frame(maxWidth: .infinity, alignment: .leading).background(DeskTheme.sheet)
                }
            } else { Text("当前没有待复习的词条。").foregroundStyle(DeskTheme.muted) }
        }
    }
}
