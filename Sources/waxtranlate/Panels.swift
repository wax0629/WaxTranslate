import SwiftUI
import Translation
import ServiceManagement

private enum Page: String, CaseIterable, Identifiable {
    case home = "首页", reading = "对照翻译", words = "生词本", settings = "设置"
    var id: Self { self }
}

struct LibraryView: View {
    @ObservedObject var notebook: Notebook
    @ObservedObject var preferences: Preferences
    @ObservedObject var document: ReadingDocument
    let shortcutErrors: () -> [String]
    let lookup: (Passage) -> Void
    let permission: () -> Void
    let speak: (String, String) -> Void
    @State private var page = Page.home
    @State private var query = ""
    @State private var reviewing = false
    @State private var revealed: UUID?
    @State private var deletion: Entry?

    var body: some View {
        VStack(spacing: 0) {
            navigation
            BookRule()
            if let error = notebook.error {
                Label(error, systemImage: "exclamationmark.triangle").font(.callout)
                    .foregroundStyle(DeskTheme.accent).padding(12).frame(maxWidth: .infinity, alignment: .leading)
            }
            switch page {
            case .home: homePage
            case .reading: ReadingPage(document: document, preferences: preferences, lookup: lookup, speak: speak)
            case .words:
                ScrollView { wordPage.padding(28).frame(maxWidth: .infinity, alignment: .leading) }
            case .settings: SettingsPage(preferences: preferences, errors: shortcutErrors(), permission: permission)
            }
        }
        .frame(minWidth: 560, minHeight: 460)
        .foregroundStyle(DeskTheme.ink).tint(DeskTheme.accent).background(DeskTheme.paper)
        .ignoresSafeArea(.container, edges: .top)
        .alert("删除这个词条？", isPresented: Binding(get: { deletion != nil }, set: { if !$0 { deletion = nil } })) {
            Button("取消", role: .cancel) { deletion = nil }
            Button("删除", role: .destructive) { if let deletion { notebook.remove(deletion.id) }; deletion = nil }
        } message: { Text("这会从本机生词本中移除词条及其复习进度。") }
    }

    private var navigation: some View {
        HStack(spacing: 20) {
            Text("WaxTranslate").font(.custom("Baskerville-SemiBoldItalic", size: 26)).accessibilityLabel("我靠翻译 WaxTranslate")
            Spacer(minLength: 4)
            ForEach(Page.allCases) { destination in
                Button { page = destination } label: {
                    Text(destination.rawValue).font(.system(size: 13, weight: page == destination ? .semibold : .regular))
                        .foregroundStyle(page == destination ? DeskTheme.ink : DeskTheme.muted)
                        .frame(height: 48).contentShape(Rectangle())
                        .overlay(alignment: .bottom) { if page == destination { Rectangle().fill(DeskTheme.ink).frame(height: 2) } }
                }.buttonStyle(.plain).accessibilityAddTraits(page == destination ? .isSelected : [])
            }
        }.padding(.leading, 90).padding(.trailing, 26)
    }

    private var homePage: some View {
        GeometryReader { geometry in
            ZStack(alignment: .topLeading) {
                MangaCover()
                ScrollView {
                    VStack(alignment: .leading, spacing: 19) {
                        Button { page = .settings } label: {
                            Text(preferences.shortcut == .disabled ? "在对照翻译中双击原文查词" : "指向生词，按 \(preferences.shortcut.hoverLabel) 查看释义")
                                .multilineTextAlignment(.leading)
                        }.buttonStyle(.plain).font(.system(size: 12))
                        TimelineView(.periodic(from: .now, by: 30)) { time in
                            VStack(alignment: .leading, spacing: 18) {
                                LazyVGrid(columns: Array(repeating: GridItem(.flexible(minimum: 160, maximum: 210), spacing: 12),
                                                         count: 2), alignment: .leading, spacing: 12) {
                                    stat(notebook.totalLookups, label: "次取词", detail: "今日 \(notebook.todayLookups(now: time.date)) 次")
                                    stat(notebook.entries.count, label: "已保存", detail: "生词本中的词条")
                                    stat(notebook.dueCount(now: time.date), label: "待复习", detail: "已到复习时间")
                                    stat(notebook.masteredCount, label: "已掌握", detail: "连续记住 3 次")
                                }.frame(maxWidth: 432, alignment: .leading)
                                recentLookups(now: time.date)
                            }
                        }
                    }
                    .padding(26)
                    .frame(width: geometry.size.width < 760 ? geometry.size.width : min(geometry.size.width * 0.64, 640), alignment: .leading)
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
        }
    }

    private func stat(_ count: Int, label: String, detail: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline, spacing: 4) {
                Text("\(count)").font(.custom("Baskerville", size: 30)).monospacedDigit()
                    .lineLimit(1).minimumScaleFactor(0.45).layoutPriority(1)
                Text(label).font(.system(size: 12)).fixedSize()
            }
            Text(detail).font(.system(size: 11)).foregroundStyle(DeskTheme.muted)
        }.padding(.horizontal, 14).padding(.vertical, 11).frame(maxWidth: .infinity, alignment: .leading)
            .background(DeskTheme.sheet.opacity(0.94), in: RoundedRectangle(cornerRadius: 9))
            .overlay { RoundedRectangle(cornerRadius: 9).strokeBorder(DeskTheme.rule, lineWidth: 0.5) }
            .accessibilityElement(children: .combine)
    }

    @ViewBuilder private func recentLookups(now: Date) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("最近取词").font(.system(size: 13, weight: .semibold))
            if notebook.recent.isEmpty {
                VStack(alignment: .leading, spacing: 12) {
                    Text("查过的词会出现在这里。").font(.callout).foregroundStyle(DeskTheme.muted)
                }.padding(.vertical, 12)
            } else {
                ForEach(notebook.recent) { recent in
                    Button { lookup(recent.passage.value) } label: {
                        HStack(spacing: 15) {
                            Text(recent.word).font(.custom("Baskerville", size: 18)).lineLimit(1)
                                .frame(maxWidth: .infinity, alignment: .leading)
                            Text(recent.displayMeaning).font(.system(size: 13)).lineLimit(1)
                                .frame(maxWidth: .infinity, alignment: .leading)
                            Text(relative(recent.date, now: now)).font(.system(size: 10)).foregroundStyle(DeskTheme.muted)
                                .frame(width: 56, alignment: .trailing)
                        }.padding(.vertical, 6).contentShape(Rectangle())
                    }.buttonStyle(.plain)
                }
            }
        }.padding(.horizontal, 4)
    }

    private func relative(_ date: Date, now: Date) -> String {
        if now.timeIntervalSince(date) < 60 { return "刚刚" }
        let formatter = RelativeDateTimeFormatter()
        formatter.locale = Locale(identifier: "zh_CN")
        formatter.unitsStyle = .short
        return formatter.localizedString(for: date, relativeTo: now)
    }

    private var wordPage: some View {
        VStack(alignment: .leading, spacing: 20) {
            HStack {
                Text("生词本").font(.system(size: 27, weight: .semibold))
                Text("\(notebook.entries.count) 条收藏").font(.callout).foregroundStyle(DeskTheme.muted)
                Spacer()
                Picker("词本模式", selection: $reviewing) {
                    Text("全部词条").tag(false)
                    Text("到期复习").tag(true)
                }.pickerStyle(.segmented).labelsHidden().frame(width: 185)
            }
            if reviewing { reviewPage } else { wordList }
        }
    }

    @ViewBuilder private var wordList: some View {
        TextField("搜索原文或译文", text: $query).textFieldStyle(.roundedBorder).accessibilityLabel("搜索词条")
        let items = notebook.entries.filter {
            query.isEmpty || $0.source.localizedCaseInsensitiveContains(query) || $0.target.localizedCaseInsensitiveContains(query)
        }
        if items.isEmpty {
            Text(query.isEmpty ? "查词时点「加入生词本」，词义和原句会保存在这里。" : "没有匹配的词条，换一个关键词试试。")
                .foregroundStyle(DeskTheme.muted).padding(.vertical, 24)
        } else {
            LazyVStack(alignment: .leading, spacing: 0) {
                ForEach(items) { item in
                    BookRule()
                    HStack(alignment: .top, spacing: 16) {
                        Button { lookup(item.passage) } label: {
                            VStack(alignment: .leading, spacing: 7) {
                                Text(item.source).font(.custom("Baskerville", size: 25))
                                Text(item.displayMeaning).font(.system(size: 15, weight: .medium))
                                if !item.context.isEmpty { Text(item.context).font(.custom("Baskerville", size: 17)).foregroundStyle(DeskTheme.muted) }
                                if let sentence = item.displaySentenceTranslation { Text(sentence).font(.callout).foregroundStyle(DeskTheme.muted) }
                            }.frame(maxWidth: .infinity, alignment: .leading).contentShape(Rectangle())
                        }.buttonStyle(.plain)
                        Button { speak(item.source, item.language ?? item.passage.sourceLanguage) } label: { Image(systemName: "speaker.wave.2") }
                            .buttonStyle(.plain).help("朗读词条").accessibilityLabel("朗读 \(item.source)")
                        Button { deletion = item } label: { Image(systemName: "trash") }
                            .buttonStyle(.plain).foregroundStyle(DeskTheme.muted).help("删除词条").accessibilityLabel("删除 \(item.source)")
                    }.padding(.vertical, 16)
                }
            }
        }
    }

    private var reviewPage: some View {
        TimelineView(.periodic(from: .now, by: 30)) { time in
            let due = notebook.entries.filter { $0.due <= time.date }
            if let item = due.min(by: { $0.due < $1.due }) {
                VStack(alignment: .leading, spacing: 18) {
                    Text("\(due.count) 条待复习").font(.callout).foregroundStyle(DeskTheme.muted)
                    HStack {
                        Text(item.source).font(.custom("Baskerville-Italic", size: 42))
                        Button { speak(item.source, item.language ?? item.passage.sourceLanguage) } label: { Image(systemName: "speaker.wave.2") }
                            .buttonStyle(.plain).accessibilityLabel("朗读复习词语")
                    }
                    if !item.context.isEmpty { Text(item.context).font(.custom("Baskerville", size: 20)) }
                    BookRule()
                    if revealed == item.id {
                        Text(item.displayMeaning).font(.title3)
                        if let sentence = item.displaySentenceTranslation { Text(sentence).foregroundStyle(DeskTheme.muted) }
                        HStack {
                            Button("再学一次") { notebook.review(item.id, remembered: false); revealed = nil }.buttonStyle(ReaderActionStyle())
                            Button("记住了") { notebook.review(item.id, remembered: true); revealed = nil }.buttonStyle(ReaderActionStyle(emphasized: true))
                        }
                    } else {
                        Button("显示释义") { revealed = item.id }.buttonStyle(ReaderActionStyle(emphasized: true))
                    }
                }.padding(24).frame(maxWidth: .infinity, alignment: .leading).background(DeskTheme.sheet, in: RoundedRectangle(cornerRadius: 12))
            } else {
                VStack(alignment: .leading, spacing: 12) {
                    Label("当前没有待复习的词条", systemImage: "checkmark.circle").font(.title3)
                    Text("到期的词条会出现在这里。").foregroundStyle(DeskTheme.muted)
                }.padding(.vertical, 24)
            }
        }
    }
}

private enum LanguageState { case checking, installed, downloadable, unsupported }

struct SettingsPage: View {
    @ObservedObject var preferences: Preferences
    let errors: [String]
    let permission: () -> Void
    @State private var captureAllowed = false
    @State private var states: [String: LanguageState] = [:]
    @State private var download: TranslationRequest?
    @State private var notice = ""
    @State private var loginEnabled = SMAppService.mainApp.status == .enabled

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 23) {
                Text("设置").font(.system(size: 27, weight: .semibold))
                VStack(alignment: .leading, spacing: 13) {
                    Text("屏幕取词").font(.headline)
                    Picker("快捷键", selection: $preferences.shortcut) {
                        ForEach(CaptureShortcut.allCases) { Text($0.title).tag($0) }
                    }.frame(maxWidth: 430, alignment: .leading)
                    Text(preferences.shortcut.help).font(.callout).foregroundStyle(DeskTheme.muted)
                    if !errors.isEmpty { Text("快捷键已被占用：" + errors.joined(separator: "、")).font(.callout).foregroundStyle(DeskTheme.accent) }
                    HStack {
                        Label(captureAllowed ? "屏幕取词已授权" : "屏幕取词待授权", systemImage: captureAllowed ? "checkmark.circle" : "lock")
                        Spacer()
                        Button("权限设置…", action: permission)
                    }.font(.callout)
                }
                BookRule()
                VStack(alignment: .leading, spacing: 13) {
                    Text("翻译语言").font(.headline)
                    Picker("源语言", selection: $preferences.language) {
                        ForEach(ReadingLanguage.allCases) { Text($0.title).tag($0) }
                    }.frame(maxWidth: 340, alignment: .leading)
                    Text("非中文译为简体中文，中文译为英语。自动识别出错时，可手动选择原文语言。").font(.callout).foregroundStyle(DeskTheme.muted)
                    ForEach(ReadingLanguage.allCases.filter { $0 != .auto }) { language in
                        languageRow(language)
                    }
                    Text("语言包由 Apple 提供，下载后可在本机使用；以当前系统显示的可用状态为准。").font(.caption).foregroundStyle(DeskTheme.muted)
                }
                BookRule()
                VStack(alignment: .leading, spacing: 13) {
                    Text("启动与参考").font(.headline)
                    Toggle("在 Dock 中显示", isOn: $preferences.showInDock)
                    Text("关闭后仍在菜单栏待命，可随时从菜单栏打开主窗口。").font(.caption).foregroundStyle(DeskTheme.muted)
                    Toggle("打开应用时显示主窗口", isOn: $preferences.showOnLaunch)
                    Toggle("登录后在菜单栏待命", isOn: Binding(get: { loginEnabled }, set: setLogin))
                    Toggle("未收录的词自动补查百科参考", isOn: $preferences.onlineReferences)
                    Text("百科查询只发送当前词语到 Wikidata，不发送原句或截图。结果单独标注为参考，可随时关闭自动查询。").font(.caption).foregroundStyle(DeskTheme.muted)
                }
                BookRule()
                HStack {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("本机词本与隐私").font(.headline)
                        Text("手动收藏与最近六次取词保存在本机。截图与其余 OCR 内容不写入文件。").font(.callout).foregroundStyle(DeskTheme.muted)
                    }
                    Spacer()
                    Button("显示数据位置") {
                        let url = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Preferences/local.luma.hovertranslate.plist")
                        NSWorkspace.shared.activateFileViewerSelecting([url])
                    }
                }
                Text("我靠翻译 · WaxTranslate " + (Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "开发版"))
                    .font(.caption).foregroundStyle(DeskTheme.muted)
                if !notice.isEmpty { Text(notice).font(.callout).foregroundStyle(DeskTheme.accent) }
            }.padding(28).frame(maxWidth: 780, alignment: .leading).frame(maxWidth: .infinity, alignment: .leading)
        }
        .task { await refresh() }
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
            captureAllowed = CGPreflightScreenCaptureAccess()
            loginEnabled = SMAppService.mainApp.status == .enabled
        }
        .background {
            if let download {
                TranslationRunner(request: download) { request, result in
                    guard self.download?.id == request.id else { return }
                    self.download = nil
                    if case .failure = result { notice = "语言包未安装完成，可重试。" }
                    Task { await refresh() }
                }.id(download.id)
            }
        }
    }

    private func languageRow(_ language: ReadingLanguage) -> some View {
        HStack {
            Text(language.title).frame(width: 68, alignment: .leading)
            Spacer()
            switch states[language.rawValue] ?? .checking {
            case .checking: Text("检查中…").foregroundStyle(DeskTheme.muted)
            case .installed: Label("已安装", systemImage: "checkmark").foregroundStyle(DeskTheme.muted)
            case .unsupported: Text("当前系统不支持").foregroundStyle(DeskTheme.muted)
            case .downloadable:
                Button(download?.source == language.rawValue ? "下载中…" : "下载语言包") {
                    notice = ""
                    download = TranslationRequest(text: "Hello", source: language.rawValue)
                }.disabled(download != nil)
            }
        }.font(.system(size: 12)).padding(.vertical, 3)
    }

    private func refresh() async {
        captureAllowed = CGPreflightScreenCaptureAccess()
        let availability = LanguageAvailability()
        for language in ReadingLanguage.allCases where language != .auto {
            let status = await availability.status(from: Locale.Language(identifier: language.rawValue),
                to: Locale.Language(identifier: language == .chinese ? "en" : "zh-Hans"))
            guard !Task.isCancelled else { return }
            switch status {
            case .installed: states[language.rawValue] = .installed
            case .supported: states[language.rawValue] = .downloadable
            default: states[language.rawValue] = .unsupported
            }
        }
    }

    private func setLogin(_ enabled: Bool) {
        do {
            if enabled { try SMAppService.mainApp.register() }
            else { try SMAppService.mainApp.unregister() }
            loginEnabled = SMAppService.mainApp.status == .enabled
            notice = loginEnabled == enabled ? "" : "请在系统设置的登录项中确认。"
        } catch { notice = "未能更改登录项，请安装应用后在系统设置中重试。" }
    }
}
