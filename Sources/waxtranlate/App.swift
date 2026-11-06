import SwiftUI
import AVFoundation

@main @MainActor final class App: NSObject, NSApplicationDelegate {
    private let notebook = Notebook()
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

    static func main() {
        let app = NSApplication.shared
        let delegate = App()
        app.delegate = delegate
        app.setActivationPolicy(.accessory)
        withExtendedLifetime(delegate) { app.run() }
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        shortcuts = Shortcuts { [weak self] id in
            if id == 1 { self?.hover() } else { self?.chooseArea() }
        }
        shortcutErrors = shortcuts.start()
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
        showLibrary()
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        showLibrary()
        return true
    }

    @objc private func quit() { NSApp.terminate(nil) }
    @objc private func showLibrary() {
        if library == nil {
            let view = LibraryView(notebook: notebook, shortcutErrors: shortcutErrors, demo: { [weak self] in
                self?.present(Passage(text: "bank", context: "They sat on the river bank and watched the water."), at: NSEvent.mouseLocation)
            }, region: { [weak self] in self?.chooseArea() }, permission: { [weak self] in self?.openPermissionSettings() })
            let window = NSWindow(contentViewController: NSHostingController(rootView: view))
            window.styleMask = [.titled, .closable, .resizable, .miniaturizable]
            window.title = "我靠翻译"
            window.setContentSize(NSSize(width: 640, height: 405))
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
        panel?.orderOut(nil)
        panel = nil
        overlay?.orderOut(nil)
        overlay = nil
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
                let passage = try await Reader.capture(point: point, region: region)
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
        show(message, at: point)
    }

    private func present(_ passage: Passage, at point: CGPoint) {
        let card = ResultCard(passage: passage, notebook: notebook, close: { [weak self] in self?.reset() },
                              speak: { [weak self] text, language in
            let utterance = AVSpeechUtterance(string: text)
            utterance.voice = AVSpeechSynthesisVoice(language: language)
            self?.voice.stopSpeaking(at: .immediate)
            self?.voice.speak(utterance)
        }, focusForDownload: { [weak self] in
            NSApp.activate(ignoringOtherApps: true)
            self?.panel?.makeKeyAndOrderFront(nil)
        })
        show(card, at: point)
    }

    private func show<V: View>(_ content: V, at point: CGPoint) {
        panel?.orderOut(nil)
        let host = NSHostingView(rootView: content)
        let size = host.fittingSize
        let window = NSPanel(contentRect: CGRect(origin: .zero, size: size), styleMask: [.titled, .nonactivatingPanel, .fullSizeContentView],
                             backing: .buffered, defer: false)
        window.titleVisibility = .hidden
        window.titlebarAppearsTransparent = true
        window.isMovableByWindowBackground = true
        window.isFloatingPanel = true
        window.hidesOnDeactivate = false
        window.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        window.contentView = host
        window.setContentSize(size)
        let area = (NSScreen.screens.first(where: { $0.frame.contains(point) }) ?? NSScreen.main)?.visibleFrame ?? .zero
        let x = min(max(area.minX, point.x + 14), area.maxX - window.frame.width)
        let below = point.y - window.frame.height - 12
        let y = below >= area.minY ? below : min(point.y + 14, area.maxY - window.frame.height)
        window.setFrameOrigin(CGPoint(x: x, y: y))
        panel = window
        window.orderFrontRegardless()
    }
}
