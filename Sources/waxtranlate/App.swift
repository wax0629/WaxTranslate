import SwiftUI
import AVFoundation
import Combine

@main @MainActor final class App: NSObject, NSApplicationDelegate, NSWindowDelegate {
    private let notebook: Notebook
    private let preferences: Preferences
    private let document = ReadingDocument()
    private let voice = AVSpeechSynthesizer()
    private var status: NSStatusItem!
    private var library: NSWindow?
    private var panel: NSPanel?
    private var overlay: SelectionPanel?
    private var job: Task<Void, Never>?
    private var shortcuts: Shortcuts!
    private var shortcutErrors: [String] = []
    private var showedPermissionHint = false
    private var requestedAccess = false
    private var settingsObserver: AnyCancellable?
    private var outsideClick: Any?
    private var pinned = false
    private var cardGeneration = UUID()

    override init() {
        let arguments = ProcessInfo.processInfo.arguments
        let defaults: UserDefaults
        if let index = arguments.firstIndex(of: "--test-profile"), index + 1 < arguments.count,
           arguments[index + 1].hasPrefix("WaxTranslate.Test."), let suite = UserDefaults(suiteName: arguments[index + 1]) {
            defaults = suite
        } else { defaults = .standard }
        notebook = Notebook(defaults: defaults)
        preferences = Preferences(defaults: defaults)
        super.init()
    }

    static func main() {
        let app = NSApplication.shared
        let delegate = App()
        app.delegate = delegate
        app.setActivationPolicy(.accessory)
        withExtendedLifetime(delegate) { app.run() }
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        installMainMenu()
        shortcuts = Shortcuts { [weak self] id in
            if id == 1 { self?.hover() } else { self?.chooseArea() }
        }
        shortcutErrors = shortcuts.start(mode: preferences.shortcut)
        settingsObserver = preferences.$shortcut.dropFirst().sink { [weak self] mode in
            self?.shortcutErrors = self?.shortcuts.start(mode: mode) ?? []
        }
        outsideClick = NSEvent.addGlobalMonitorForEvents(matching: [.leftMouseDown, .rightMouseDown]) { [weak self] _ in
            Task { @MainActor in
                guard let self, !self.pinned, let panel = self.panel, !panel.frame.contains(NSEvent.mouseLocation) else { return }
                self.reset()
            }
        }
        status = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        status.button?.image = NSImage(systemSymbolName: "character.book.closed", accessibilityDescription: "我靠翻译")
        status.button?.toolTip = "我靠翻译"
        let menu = NSMenu()
        for (title, action) in [("打开我靠翻译", #selector(showLibrary)), ("区域翻译…", #selector(chooseArea)),
                                 ("退出我靠翻译", #selector(quit))] {
            let item = menu.addItem(withTitle: title, action: action, keyEquivalent: "")
            item.target = self
        }
        status.menu = menu
        if preferences.showOnLaunch || ProcessInfo.processInfo.arguments.contains("--show") { showLibrary() }
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        showLibrary()
        return true
    }

    @objc private func quit() { NSApp.terminate(nil) }

    private func installMainMenu() {
        let bar = NSMenu()
        let applicationItem = NSMenuItem()
        let application = NSMenu(title: "我靠翻译")
        let open = NSMenuItem(title: "打开我靠翻译", action: #selector(showLibrary), keyEquivalent: "0")
        open.target = self
        application.addItem(open)
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
                }, region: { [weak self] in self?.chooseArea() }, permission: { [weak self] in self?.openPermissionSettings() },
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

    private func hover() {
        guard readyToCapture() else { return }
        reset()
        translate(at: NSEvent.mouseLocation, region: nil)
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

    private func readyToCapture() -> Bool {
        if CGPreflightScreenCaptureAccess() {
            showedPermissionHint = false
            return true
        }
        if !showedPermissionHint {
            showedPermissionHint = true
            reset()
            showError(ReaderError.permission, at: NSEvent.mouseLocation)
        }
        return false
    }

    private func translate(at point: CGPoint, region: CGRect?) {
        job = Task {
            do {
                // Let the window server remove our previous panel or selection overlay.
                try await Task.sleep(nanoseconds: 110_000_000)
                let passage = try await Reader.capture(point: point, region: region, language: preferences.language.rawValue)
                try Task.checkCancellation()
                present(passage, at: point)
            } catch {
                guard !Task.isCancelled else { return }
                if case ReaderError.permission = error { showedPermissionHint = true }
                showError(error, at: point)
            }
        }
    }

    private func showError(_ error: Error, at point: CGPoint) {
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
        show(message, at: point)
    }

    private func present(_ passage: Passage, at point: CGPoint, focus: Bool = false) {
        let generation = UUID()
        cardGeneration = generation
        let card = ResultCard(passage: passage, notebook: notebook, preferences: preferences, close: { [weak self] in self?.reset() },
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
        })
        show(card, at: point, focus: focus)
    }

    private func speak(_ text: String, language: String) {
        guard !text.isEmpty else { return }
        let utterance = AVSpeechUtterance(string: text)
        utterance.voice = AVSpeechSynthesisVoice(language: language)
        voice.stopSpeaking(at: .immediate)
        voice.speak(utterance)
    }

    private func show<V: View>(_ content: V, at point: CGPoint, focus: Bool = false) {
        dismissPanel()
        let host = NSHostingView(rootView: content)
        let size = host.fittingSize
        let window = LookupPanel(contentRect: CGRect(origin: .zero, size: size), styleMask: [.borderless, .nonactivatingPanel],
                             backing: .buffered, defer: false)
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
        window.contentView = host
        host.wantsLayer = true
        host.layer?.cornerRadius = 12
        host.layer?.masksToBounds = true
        window.setContentSize(size)
        let area = (NSScreen.screens.first(where: { $0.frame.contains(point) }) ?? NSScreen.main)?.visibleFrame ?? .zero
        let x = min(max(area.minX, point.x + 14), area.maxX - window.frame.width)
        let below = point.y - window.frame.height - 12
        let y = below >= area.minY ? below : min(point.y + 14, area.maxY - window.frame.height)
        window.setFrameOrigin(CGPoint(x: x, y: y))
        panel = window
        window.delegate = self
        if focus {
            NSApp.activate(ignoringOtherApps: true)
            window.makeKeyAndOrderFront(nil)
            window.makeMain()
        } else if NSApp.isActive { window.makeKeyAndOrderFront(nil) }
        else { window.orderFrontRegardless() }
    }
}

private final class LookupPanel: NSPanel {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { true }
}
