import SwiftUI
import AVFoundation
import Combine

#if !WAX_APP_TESTS
@main
#endif
@MainActor final class App: NSObject, NSApplicationDelegate, NSWindowDelegate {
    private let notebook: Notebook
    private let preferences: Preferences
    private let testHover: Bool
    private let document = ReadingDocument()
    private let voice = AVSpeechSynthesizer()
    private var status: NSStatusItem!
    private var library: NSWindow?
    private var captureFixture: NSWindow?
    private(set) var panel: NSPanel?
    private var overlay: SelectionPanel?
    private(set) var job: Task<Void, Never>?
    private let hoverCache = Reader.HoverCache()
    private var ocrWarmup: Task<Void, Never>?
    private var shortcuts: Shortcuts!
    private var shortcutErrors: [String] = []
    private let captureAccess: () -> Bool
    private var requestedAccess = false
    private var settingsObserver: AnyCancellable?
    private var dockObserver: AnyCancellable?
    private var outsideClick: Any?
    private var pinned = false
    private var cardGeneration = UUID()

    override convenience init() {
        self.init(defaults: nil, captureAccess: CGPreflightScreenCaptureAccess)
    }

    init(defaults testDefaults: UserDefaults?, captureAccess: @escaping () -> Bool) {
        self.captureAccess = captureAccess
        let arguments = ProcessInfo.processInfo.arguments
        let defaults: UserDefaults
        if let testDefaults {
            defaults = testDefaults
            testHover = false
        } else if let index = arguments.firstIndex(of: "--test-profile"), index + 1 < arguments.count,
           arguments[index + 1].hasPrefix("WaxTranslate.Test."), let suite = UserDefaults(suiteName: arguments[index + 1]) {
            defaults = suite
            testHover = arguments.contains("--test-hover")
        } else { defaults = .standard; testHover = false }
        notebook = Notebook(defaults: defaults)
        preferences = Preferences(defaults: defaults)
        super.init()
    }

    static func main() {
        let app = NSApplication.shared
        let delegate = App()
        app.delegate = delegate
        app.setActivationPolicy(delegate.preferences.showInDock ? .regular : .accessory)
        withExtendedLifetime(delegate) { app.run() }
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        installMainMenu()
        if let url = Bundle.main.url(forResource: "AppIcon", withExtension: "icns"), let icon = NSImage(contentsOf: url) {
            NSApp.applicationIconImage = icon
        }
        shortcuts = Shortcuts { [weak self] id in
            if id == 1 { self?.hover() } else { self?.chooseArea() }
        }
        shortcutErrors = shortcuts.start(mode: preferences.shortcut)
        settingsObserver = preferences.$shortcut.dropFirst().sink { [weak self] mode in
            self?.shortcutErrors = self?.shortcuts.start(mode: mode) ?? []
        }
        dockObserver = preferences.$showInDock.dropFirst().sink { [weak self] visible in
            self?.setDockVisible(visible)
        }
        outsideClick = NSEvent.addGlobalMonitorForEvents(matching: [.leftMouseDown, .rightMouseDown]) { [weak self] _ in
            Task { @MainActor in
                guard let self, !self.pinned, let panel = self.panel, !panel.frame.contains(NSEvent.mouseLocation) else { return }
                self.reset()
            }
        }
        status = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        if let url = Bundle.main.url(forResource: "AppIcon", withExtension: "icns"), let icon = NSImage(contentsOf: url) {
            icon.size = NSSize(width: 20, height: 20)
            icon.accessibilityDescription = "我靠翻译"
            status.button?.image = icon
        }
        status.button?.toolTip = "我靠翻译"
        let menu = NSMenu()
        for (title, action) in [("打开我靠翻译", #selector(showLibrary)), ("框选翻译…", #selector(chooseArea)),
                                 ("退出我靠翻译", #selector(quit))] {
            let item = menu.addItem(withTitle: title, action: action, keyEquivalent: "")
            item.target = self
        }
        status.menu = menu
        // The UI harness can exercise real screen capture without synthesizing
        // a modifier-only key. This is accepted only with an isolated test suite.
        if testHover { runCaptureFixture() }
        else if let index = ProcessInfo.processInfo.arguments.firstIndex(of: "--test-card"),
                ProcessInfo.processInfo.arguments.contains("--test-profile"),
                index + 1 < ProcessInfo.processInfo.arguments.count,
                let recent = notebook.recent.first(where: { $0.word == ProcessInfo.processInfo.arguments[index + 1] }) {
            present(recent.passage.value, at: CGPoint(x: NSScreen.main?.visibleFrame.midX ?? 400, y: NSScreen.main?.visibleFrame.midY ?? 400), focus: true)
        }
        else if preferences.showOnLaunch || ProcessInfo.processInfo.arguments.contains("--show") { showLibrary() }
        if !testHover || ProcessInfo.processInfo.arguments.contains("--test-hover-series") {
            TranslationWarmup.start()
            if preferences.shortcut != .disabled, captureAccess() {
                let language = preferences.language.rawValue
                ocrWarmup = Task.detached(priority: .utility) { await Reader.warmUp(language: language) }
            }
        }
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        if testHover { return false }
        if let panel, panel.isVisible {
            panel.makeKeyAndOrderFront(nil)
            return true
        }
        showLibrary()
        return true
    }

    @objc private func quit() { NSApp.terminate(nil) }

    private func runCaptureFixture() {
        guard readyToCapture(), let screen = NSScreen.main else {
            if ProcessInfo.processInfo.arguments.contains("--test-hover-series") || ProcessInfo.processInfo.arguments.contains("--test-hover-checks") {
                FileHandle.standardError.write(Data("Hover fixture requires a display and existing screen capture permission.\n".utf8))
                exit(1)
            }
            return
        }
        let view = CaptureFixtureView(frame: NSRect(x: 0, y: 0, width: min(1200, screen.visibleFrame.width - 40), height: 240))
        let fixture = NSWindow(contentRect: view.frame, styleMask: [.titled, .closable], backing: .buffered, defer: false)
        fixture.title = "WaxTranslate · 隔离屏幕取词测试"
        fixture.level = .floating
        fixture.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        fixture.contentView = view
        let available = screen.visibleFrame
        fixture.setFrameOrigin(NSPoint(x: available.midX - fixture.frame.width / 2,
                                       y: available.minY + max(0, available.height - fixture.frame.height) / 5))
        fixture.isReleasedWhenClosed = false
        captureFixture = fixture
        NSApp.activate(ignoringOtherApps: true)
        fixture.makeKeyAndOrderFront(nil)
        view.displayIfNeeded()
        func sample(_ word: String) -> CGPoint {
            fixture.convertPoint(toScreen: view.convert(view.samplePoint(for: word), to: nil))
        }
        #if WAX_HOVER_CHECKS
        if ProcessInfo.processInfo.arguments.contains("--test-hover-checks") {
            Task {
                do {
                    try await checkHoverFeedback(sample: sample, sentence: view.sentence, notebook: notebook) { rect in
                        self.chooseArea()
                        (self.overlay?.contentView as? SelectionView)?.finish(rect)
                    }
                    FileHandle.standardError.write(Data("Passed: pending, same-window result, occlusion, replacement, close, region and empty capture.\n".utf8))
                    NSApp.terminate(nil)
                } catch {
                    FileHandle.standardError.write(Data("Hover feedback check failed: \(error)\n".utf8))
                    exit(1)
                }
            }
            return
        }
        #endif
        guard ProcessInfo.processInfo.arguments.contains("--test-hover-series") else { hover(at: sample("out")); return }
        Task {
            // A menu bar app is usually already resident when the reader looks up the first word.
            try await Task.sleep(nanoseconds: 6_000_000_000)
            for word in ["out", "results", "out", "results", "out"] {
                hover(at: sample(word))
                await job?.value
                let shown = (panel?.contentView as? NSHostingView<ResultCard>)?.rootView.passage
                guard shown?.text == (word == "out" ? "rule out" : word), shown?.context == view.sentence else {
                    FileHandle.standardError.write(Data("Hover fixture failed to show the expected word and sentence.\n".utf8))
                    exit(1)
                }
                try await Task.sleep(nanoseconds: 1_000_000_000)
            }
            NSApp.terminate(nil)
        }
    }

    private func setDockVisible(_ visible: Bool) {
        let focused = NSApp.keyWindow
        let active = NSApp.isActive
        guard NSApp.setActivationPolicy(visible ? .regular : .accessory) else {
            preferences.showInDock = NSApp.activationPolicy() == .regular
            return
        }
        // Changing activation policy can briefly deactivate the app. Keep the
        // settings window and the user's current editing state in place.
        if active {
            DispatchQueue.main.async {
                NSApp.activate(ignoringOtherApps: true)
                focused?.makeKeyAndOrderFront(nil)
            }
        }
    }

    private func installMainMenu() {
        let bar = NSMenu()
        let applicationItem = NSMenuItem()
        let application = NSMenu(title: "我靠翻译")
        let open = NSMenuItem(title: "打开我靠翻译", action: #selector(showLibrary), keyEquivalent: "0")
        open.target = self
        application.addItem(open)
        let area = NSMenuItem(title: "框选翻译…", action: #selector(chooseArea), keyEquivalent: "")
        area.target = self
        application.addItem(area)
        application.addItem(.separator())
        let quit = NSMenuItem(title: "退出我靠翻译", action: #selector(quit), keyEquivalent: "q")
        quit.target = self
        application.addItem(quit)
        applicationItem.submenu = application
        bar.addItem(applicationItem)
        let editItem = NSMenuItem()
        let edit = NSMenu(title: "编辑")
        for (title, action, key) in [("撤销", Selector(("undo:")), "z"),
                                    ("剪切", #selector(NSText.cut(_:)), "x"),
                                    ("复制", #selector(NSText.copy(_:)), "c"),
                                    ("粘贴", #selector(NSText.paste(_:)), "v"),
                                    ("全选", #selector(NSText.selectAll(_:)), "a")] {
            edit.addItem(withTitle: title, action: action, keyEquivalent: key)
        }
        editItem.submenu = edit
        bar.addItem(editItem)
        let windowItem = NSMenuItem()
        let window = NSMenu(title: "窗口")
        window.addItem(withTitle: "关闭窗口", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w")
        windowItem.submenu = window
        bar.addItem(windowItem)
        NSApp.mainMenu = bar
        NSApp.windowsMenu = window
    }
    @objc private func showLibrary() {
        if library == nil {
            let view = LibraryView(notebook: notebook, preferences: preferences, document: document,
                shortcutErrors: { [weak self] in self?.shortcutErrors ?? [] }, lookup: { [weak self] passage in
                    self?.reset()
                    self?.present(passage, at: NSEvent.mouseLocation, focus: true)
                }, permission: { [weak self] in self?.openPermissionSettings() },
                speak: { [weak self] text, language in self?.speak(text, language: language) })
            let window = NSWindow(contentViewController: NSHostingController(rootView: view))
            window.styleMask = [.titled, .closable, .resizable, .miniaturizable, .fullSizeContentView]
            window.title = "我靠翻译"
            window.titleVisibility = .hidden
            window.titlebarAppearsTransparent = true
            window.titlebarSeparatorStyle = .none
            window.isMovableByWindowBackground = true
            let available = NSScreen.main?.visibleFrame.size ?? NSSize(width: 880, height: 600)
            window.setContentSize(NSSize(width: min(980, available.width - 32), height: min(620, available.height - 66)))
            window.center()
            window.isReleasedWhenClosed = false
            library = window
        }
        NSApp.activate(ignoringOtherApps: true)
        library?.makeKeyAndOrderFront(nil)
    }

    private func openPermissionSettings() {
        // Only the settings button can trigger the macOS consent flow.
        if !CGPreflightScreenCaptureAccess(), !requestedAccess {
            requestedAccess = true
            _ = CGRequestScreenCaptureAccess()
        }
        if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture") {
            NSWorkspace.shared.open(url)
        }
    }

    private func reset() {
        job?.cancel()
        dismissPanel()
        overlay?.orderOut(nil)
        overlay = nil
        pinned = false
    }

    private func dismissPanel() {
        // Unmount SwiftUI so its translation and network tasks are cancelled,
        // rather than leaving a hidden card alive after a replacement query.
        let previous = panel
        panel = nil
        previous?.contentView = nil
        previous?.orderOut(nil)
        previous?.close()
    }

    func windowWillClose(_ notification: Notification) {
        if let window = notification.object as? NSWindow, window === panel { reset() }
    }

    func hover(at point: CGPoint = NSEvent.mouseLocation) {
        let trace = LookupTrace()
        guard readyToCapture() else { return }
        reset()
        translate(at: point, region: nil, trace: trace)
    }

    @objc private func chooseArea() {
        guard readyToCapture() else { return }
        reset()
        let point = NSEvent.mouseLocation
        guard let screen = NSScreen.screens.first(where: { $0.frame.contains(point) }) else { return }
        let window = SelectionPanel(contentRect: screen.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.level = .screenSaver
        window.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        window.isOpaque = false
        window.backgroundColor = .clear
        window.hasShadow = false
        window.hidesOnDeactivate = false
        let selector = SelectionView(frame: CGRect(origin: .zero, size: screen.frame.size))
        selector.finish = { [weak self] rect in
            self?.overlay?.orderOut(nil)
            self?.overlay = nil
            if let rect { self?.translate(at: CGPoint(x: rect.midX, y: rect.midY), region: rect) }
        }
        window.contentView = selector
        overlay = window
        NSApp.activate(ignoringOtherApps: true)
        window.makeKeyAndOrderFront(nil)
        window.makeFirstResponder(selector)
    }

    func readyToCapture() -> Bool {
        if captureAccess() { return true }
        // Replace the previous panel on each attempt. Closing a hint must not
        // permanently silence later requests in the same process.
        reset()
        showError(ReaderError.permission, at: NSEvent.mouseLocation)
        return false
    }

    private func translate(at point: CGPoint, region: CGRect?, trace: LookupTrace = LookupTrace()) {
        ocrWarmup?.cancel()
        ocrWarmup = nil
        // Capture can start while the main thread lays out the waiting card.
        let windows = NSApp.windows.compactMap { window -> CGWindowID? in
            guard window.isVisible, !(window is LookupPanel), !(window is SelectionPanel) else { return nil }
            return CGWindowID(exactly: window.windowNumber)
        }
        let display = Reader.Display(at: point), language = preferences.language.rawValue
        let capture = Task.detached(priority: .userInitiated) { [hoverCache] in
            try await Reader.capture(point: point, region: region, display: display, language: language, readableWindows: Set(windows),
                                     hoverCache: hoverCache, trace: trace)
        }
        let pending: NSPanel?
        if region == nil {
            let began = LookupTrace.now
            pending = show(PendingLookupCard(close: { [weak self] in self?.reset() }), at: point, focus: testHover)
            trace.record("lookup.pending_shown", since: began)
        } else { pending = nil }
        job = Task {
            do {
                let passage = try await withTaskCancellationHandler { try await capture.value } onCancel: { capture.cancel() }
                try Task.checkCancellation()
                guard pending == nil || panel === pending else { return }
                present(passage, at: point, focus: testHover, trace: trace, pending: pending)
            } catch {
                guard !Task.isCancelled, pending == nil || panel === pending else { return }
                showError(error, at: point, pending: pending)
            }
        }
    }

    private func showError(_ error: Error, at point: CGPoint, pending: NSPanel? = nil) {
        let message = VStack(alignment: .leading, spacing: 12) {
            Text(error.localizedDescription).fixedSize(horizontal: false, vertical: true)
            HStack {
                if case ReaderError.permission = error {
                    Button("打开系统设置") { [weak self] in self?.openPermissionSettings() }
                }
                Spacer()
                Button("关闭") { [weak self] in self?.reset() }
            }
        }.padding().frame(width: 330)
            .foregroundStyle(DeskTheme.ink).tint(DeskTheme.accent).background(DeskTheme.sheet)
        show(message, at: point, focus: testHover, updating: pending)
    }

    private func present(_ passage: Passage, at point: CGPoint, focus: Bool = false, trace: LookupTrace = LookupTrace(), pending: NSPanel? = nil) {
        let began = LookupTrace.now
        let generation = UUID()
        cardGeneration = generation
        let card = ResultCard(passage: passage, notebook: notebook, preferences: preferences, trace: trace, close: { [weak self] in self?.reset() },
                              speak: { [weak self] text, language in
            self?.speak(text, language: language)
        }, focusForDownload: { [weak self] in
            NSApp.activate(ignoringOtherApps: true)
            self?.panel?.makeKeyAndOrderFront(nil)
        }, pin: { [weak self] pinned in self?.pinned = pinned }, resize: { [weak self] size in
            guard let self, self.cardGeneration == generation, let panel = self.panel, size.height > 0 else { return }
            let top = panel.frame.maxY
            panel.setContentSize(size)
            let area = (NSScreen.screens.first(where: { $0.frame.contains(panel.frame.origin) }) ?? NSScreen.main)?.visibleFrame ?? .zero
            panel.setFrameOrigin(CGPoint(x: min(max(area.minX, panel.frame.minX), area.maxX - panel.frame.width),
                                         y: max(area.minY, min(top - panel.frame.height, area.maxY - panel.frame.height))))
        }, query: { [weak self] next in self?.present(next, at: point, focus: true) })
        show(card, at: point, focus: focus, updating: pending)
        trace.record("lookup.card_shown", since: began)
    }

    private func speak(_ text: String, language: String) {
        guard !text.isEmpty else { return }
        let utterance = AVSpeechUtterance(string: text)
        utterance.voice = AVSpeechSynthesisVoice(language: language)
        voice.stopSpeaking(at: .immediate)
        voice.speak(utterance)
    }

    private func makePanel() -> LookupPanel {
        let window = LookupPanel(contentRect: .zero, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        window.title = "取词结果"
        window.titleVisibility = .hidden
        window.isReleasedWhenClosed = false
        window.isOpaque = false
        window.backgroundColor = .clear
        window.hasShadow = true
        window.titlebarAppearsTransparent = true
        window.isMovableByWindowBackground = true
        window.isFloatingPanel = true
        window.hidesOnDeactivate = false
        window.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        window.delegate = self
        return window
    }

    @discardableResult
    private func show<V: View>(_ content: V, at point: CGPoint, focus: Bool = false, updating: NSPanel? = nil) -> NSPanel {
        if updating == nil { dismissPanel() }
        let window = updating ?? makePanel()
        let host = NSHostingView(rootView: content)
        let size = host.fittingSize
        host.wantsLayer = true
        host.layer?.cornerRadius = 12
        host.layer?.masksToBounds = true
        window.contentView = host
        window.setContentSize(size)
        let area = (NSScreen.screens.first(where: { $0.frame.contains(point) }) ?? NSScreen.main)?.visibleFrame ?? .zero
        let x = min(max(area.minX, point.x + 14), area.maxX - window.frame.width)
        let below = point.y - window.frame.height - 12
        let y = below >= area.minY ? below : min(point.y + 14, area.maxY - window.frame.height)
        window.setFrameOrigin(CGPoint(x: x, y: y))
        panel = window
        #if WAX_APP_TESTS
        window.setFrameOrigin(NSPoint(x: -20000, y: -20000))
        #else
        if updating != nil { return window }
        if focus {
            NSApp.activate(ignoringOtherApps: true)
            window.makeKeyAndOrderFront(nil)
            window.makeMain()
        } else if NSApp.isActive { window.makeKeyAndOrderFront(nil) }
        else { window.orderFrontRegardless() }
        #endif
        return window
    }

    #if WAX_APP_TESTS
    var testPanel: NSPanel? { panel }
    #endif
}

struct PendingLookupCard: View {
    let close: () -> Void

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: "text.magnifyingglass").foregroundStyle(DeskTheme.muted).accessibilityHidden(true)
            Text("正在取词…").font(.callout)
            Spacer()
            Button(action: close) { Image(systemName: "xmark") }
                .buttonStyle(.plain).help("关闭").accessibilityLabel("关闭取词卡").keyboardShortcut(.cancelAction)
        }
        .padding(19).frame(width: 365)
        .foregroundStyle(DeskTheme.ink).background(DeskTheme.sheet)
    }
}

private final class LookupPanel: NSPanel {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { true }
}

private final class CaptureFixtureView: NSView {
    let sentence = "These results do not rule out infection."
    private let font = NSFont.systemFont(ofSize: 24)
    private var textOrigin: CGPoint {
        let width = (sentence as NSString).size(withAttributes: [.font: font]).width
        return CGPoint(x: max(0, (bounds.width - width) / 2), y: 110)
    }
    func samplePoint(for word: String) -> CGPoint {
        let prefix = sentence.components(separatedBy: word)[0] as NSString
        return CGPoint(x: textOrigin.x + prefix.size(withAttributes: [.font: font]).width + (word as NSString).size(withAttributes: [.font: font]).width / 2,
                       y: textOrigin.y + font.ascender * 0.55)
    }
    override func draw(_ dirtyRect: NSRect) {
        NSColor.white.setFill(); bounds.fill()
        (sentence as NSString).draw(at: textOrigin, withAttributes: [.font: font, .foregroundColor: NSColor.black])
    }
}
