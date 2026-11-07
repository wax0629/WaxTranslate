import SwiftUI

private enum Page: String, CaseIterable, Identifiable {
    case start = "工作台", words = "生词本", review = "复习"
    var id: Self { self }
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
        VStack(spacing: 0) {
            HStack(spacing: 0) {
                HStack(alignment: .firstTextBaseline, spacing: 2) {
                    Text("WaxTranslate").font(.custom("Baskerville-SemiBold", size: 28))
                    Circle().fill(DeskTheme.accent).frame(width: 5, height: 5)
                }.accessibilityElement(children: .combine)
                Spacer()
                HStack(spacing: 22) {
                    ForEach(Page.allCases) { destination in
                        Button { page = destination } label: {
                            Text(destination.rawValue)
                                .font(.system(size: 13, weight: page == destination ? .semibold : .regular))
                                .foregroundStyle(page == destination ? DeskTheme.ink : DeskTheme.muted)
                                .padding(.horizontal, 1).frame(height: 58)
                                .overlay(alignment: .bottom) {
                                    if page == destination { Rectangle().fill(DeskTheme.accent).frame(height: 2) }
                                }
                                .contentShape(Rectangle())
                        }.buttonStyle(.plain).accessibilityAddTraits(page == destination ? .isSelected : [])
                    }
                }
            }.padding(.horizontal, 30)
            BookRule()
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    switch page {
                    case .start: startPage
                    case .words: wordList
                    case .review: reviewPage
                    }
                }
                .padding(.horizontal, 30).padding(.top, 23).padding(.bottom, 24)
                .frame(maxWidth: 1040, alignment: .leading).frame(maxWidth: .infinity)
            }.frame(maxHeight: .infinity)
        }
        .frame(minWidth: 515, minHeight: 380)
        .foregroundStyle(DeskTheme.ink).tint(DeskTheme.accent).background(DeskTheme.paper)
        .onAppear { captureAllowed = CGPreflightScreenCaptureAccess() }
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
            captureAllowed = CGPreflightScreenCaptureAccess()
        }
    }

    @ViewBuilder private var startPage: some View {
        Button(action: demo) {
            GeometryReader { bounds in
                VStack(alignment: .leading, spacing: 0) {
                    HStack(spacing: 8) {
                        Image(systemName: "character.book.closed")
                        Text("语境试读")
                    }.font(.system(size: 12, weight: .semibold))
                    Spacer(minLength: 12)
                    HStack(alignment: .firstTextBaseline, spacing: 12) {
                        Text("bank").font(.custom("Baskerville-Italic", size: 84))
                        Text("/bæŋk/").font(.custom("Baskerville", size: 19))
                    }
                    Text("They sat on the river bank and watched the water.")
                        .font(.custom("Baskerville", size: 19)).lineSpacing(2)
                        .frame(maxWidth: bounds.size.width * 0.54, alignment: .leading)
                    Spacer(minLength: 13)
                    HStack(spacing: 12) {
                        Text("试译示例")
                        Image(systemName: "arrow.up.right")
                    }
                    .font(.system(size: 12, weight: .semibold)).foregroundStyle(DeskTheme.coverInk)
                    .padding(.horizontal, 13).frame(height: 29).background(.white, in: Capsule())
                }
                .foregroundStyle(.white).padding(.horizontal, 26).padding(.vertical, 22)
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
                .background(RiverCover()).clipShape(RoundedRectangle(cornerRadius: 10))
                .contentShape(RoundedRectangle(cornerRadius: 10))
            }.frame(height: 258)
        }.buttonStyle(.plain).accessibilityLabel("试译示例 bank").accessibilityHint("查看例句中的词义")

        VStack(alignment: .leading, spacing: 12) {
            Text("屏幕翻译").font(.system(size: 19, weight: .semibold))
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 25) {
                    hoverHelp.frame(minWidth: 245)
                    Rectangle().fill(DeskTheme.rule).frame(width: 1, height: 48)
                    regionHelp.frame(minWidth: 245)
                }
                VStack(alignment: .leading, spacing: 14) { hoverHelp; BookRule(); regionHelp }
            }
        }
        if !shortcutErrors.isEmpty {
            Text("快捷键已被占用：" + shortcutErrors.joined(separator: "、"))
                .font(.callout).foregroundStyle(DeskTheme.accent)
        }
        VStack(spacing: 12) {
            BookRule()
            HStack {
                Label(captureAllowed ? "屏幕取词已授权" : "屏幕取词待授权",
                      systemImage: captureAllowed ? "checkmark.circle" : "lock")
                Spacer()
                Button(action: permission) {
                    HStack(spacing: 5) { Text("权限设置"); Image(systemName: "arrow.up.right") }
                }.buttonStyle(.plain)
            }.font(.system(size: 12)).foregroundStyle(DeskTheme.muted)
        }
    }

    private var hoverHelp: some View {
        shortcut("悬停取词", symbol: "cursorarrow.rays", keys: "⌥ ⇧ T", hint: "指向其他应用中的词，按快捷键查看释义。")
    }

    private var regionHelp: some View {
        Button(action: region) {
            shortcut("框选翻译", symbol: "viewfinder", keys: "⌥ ⇧ R", hint: "点此开始框选，拖动选区，按 Esc 取消。")
        }.buttonStyle(.plain)
    }

    private func shortcut(_ title: String, symbol: String, keys: String, hint: String) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: symbol).font(.system(size: 15, weight: .medium)).foregroundStyle(DeskTheme.accent)
                .frame(width: 32, height: 32).background(DeskTheme.soft, in: Circle())
            VStack(alignment: .leading, spacing: 6) {
                HStack {
                    Text(title).font(.system(size: 14, weight: .semibold))
                    Spacer(minLength: 5)
                    Text(keys).font(.system(size: 11, weight: .medium, design: .monospaced))
                        .foregroundStyle(DeskTheme.muted).padding(.horizontal, 6).padding(.vertical, 2)
                        .overlay { RoundedRectangle(cornerRadius: 4).strokeBorder(DeskTheme.rule, lineWidth: 1) }
                }
                Text(hint).font(.system(size: 12)).foregroundStyle(DeskTheme.muted)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }.frame(maxWidth: .infinity, alignment: .leading).contentShape(Rectangle())
    }

    @ViewBuilder private var wordList: some View {
        HStack(alignment: .firstTextBaseline, spacing: 10) {
            Text("生词本").font(.system(size: 29, weight: .semibold))
            Text("\(notebook.entries.count) 条收藏").font(.callout).foregroundStyle(DeskTheme.muted)
        }
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass").foregroundStyle(DeskTheme.muted)
            TextField("搜索原文或译文", text: $query).textFieldStyle(.plain)
        }
        .padding(.horizontal, 12).frame(minHeight: 36)
        .background(DeskTheme.sheet, in: RoundedRectangle(cornerRadius: 6))
        .overlay { RoundedRectangle(cornerRadius: 6).strokeBorder(DeskTheme.rule, lineWidth: 1).allowsHitTesting(false) }
        let items = notebook.entries.filter {
            query.isEmpty || $0.source.localizedCaseInsensitiveContains(query) || $0.target.localizedCaseInsensitiveContains(query)
        }
        if items.isEmpty {
            emptyState(query.isEmpty ? "还没有收藏的词" : "没有匹配的词条", icon: "bookmark",
                       detail: query.isEmpty ? "查词时点「加入生词本」，词义和原句会保存在这里。" : "换一个单词或译文试试。")
        } else {
            LazyVStack(alignment: .leading, spacing: 0) {
                ForEach(items) { item in
                    BookRule()
                    HStack(alignment: .top, spacing: 12) {
                        VStack(alignment: .leading, spacing: 7) {
                            Text(item.source).font(.custom("Baskerville-SemiBold", size: 27))
                            Text(item.displayMeaning).font(.system(size: 15, weight: .medium))
                            if !item.context.isEmpty {
                                Text(item.context).font(.custom("Baskerville", size: 17)).foregroundStyle(DeskTheme.muted)
                            }
                            if let sentence = item.sentenceTranslation { Text(sentence).font(.callout).foregroundStyle(DeskTheme.muted) }
                        }.textSelection(.enabled)
                        Spacer()
                        Button { notebook.remove(item.id) } label: {
                            Image(systemName: "trash").padding(6)
                        }.buttonStyle(.plain).foregroundStyle(DeskTheme.muted).accessibilityLabel("删除词条").help("删除词条")
                    }.padding(.vertical, 13)
                }
            }
        }
    }

    @ViewBuilder private var reviewPage: some View {
        Text("复习").font(.system(size: 29, weight: .semibold))
        TimelineView(.periodic(from: .now, by: 30)) { time in
            let due = notebook.entries.filter { $0.due <= time.date }
            if let item = due.min(by: { $0.due < $1.due }) {
                VStack(alignment: .leading, spacing: 15) {
                    Label("\(due.count) 条待复习", systemImage: "bookmark").font(.callout).foregroundStyle(DeskTheme.accent)
                    Text(item.source).font(.custom("Baskerville-Italic", size: 42))
                    if !item.context.isEmpty { Text(item.context).font(.custom("Baskerville", size: 20)) }
                    BookRule()
                    if revealed == item.id {
                        Text(item.displayMeaning).font(.title3)
                        if let sentence = item.sentenceTranslation { Text(sentence).foregroundStyle(DeskTheme.muted) }
                        HStack {
                            Button("再学一次") { notebook.review(item.id, remembered: false); revealed = nil }
                                .buttonStyle(ReaderActionStyle())
                            Button("记住了") { notebook.review(item.id, remembered: true); revealed = nil }
                                .buttonStyle(ReaderActionStyle(emphasized: true))
                        }
                    } else {
                        Button("显示释义") { revealed = item.id }.buttonStyle(ReaderActionStyle(emphasized: true))
                    }
                }
                .padding(24).frame(maxWidth: .infinity, alignment: .leading)
                .background(DeskTheme.sheet, in: RoundedRectangle(cornerRadius: 10))
            } else {
                emptyState("当前没有待复习的词条", icon: "checkmark.circle", detail: "到期的词条会出现在这里。")
            }
        }
    }

    private func emptyState(_ title: String, icon: String, detail: String) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Image(systemName: icon).font(.system(size: 22)).foregroundStyle(DeskTheme.accent)
            Text(title).font(.headline)
            Text(detail).foregroundStyle(DeskTheme.muted)
        }
        .padding(24).frame(maxWidth: .infinity, alignment: .leading)
        .background(DeskTheme.sheet, in: RoundedRectangle(cornerRadius: 8))
    }
}
