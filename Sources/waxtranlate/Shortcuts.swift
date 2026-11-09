import Carbon
import AppKit

// A modifier shortcut fires on release only when nothing else happened during
// the tap. Event counters also catch a letter pressed and released between the
// two flagsChanged callbacks, without recording text or installing a key tap.
struct OptionTapTracker {
    private var press: (time: TimeInterval, keys: UInt32, pointer: UInt32, modifiers: UInt32)?
    private var held = false

    mutating func update(optionDown: Bool, blocked: Bool, time: TimeInterval,
                         keys: UInt32, pointer: UInt32, modifiers: UInt32) -> Bool {
        if optionDown {
            if blocked { press = nil }
            else if !held { press = (time, keys, pointer, modifiers) }
            held = true
            return false
        }
        defer { press = nil; held = false }
        guard let press, !blocked else { return false }
        return time >= press.time && time - press.time <= 0.45 && keys == press.keys && pointer == press.pointer
            && modifiers == press.modifiers &+ 1
    }
}

final class Shortcuts {
    private var refs: [EventHotKeyRef] = []
    private var handler: EventHandlerRef?
    private var globalOptionMonitor: Any?
    private var localOptionMonitor: Any?
    private var optionTap = OptionTapTracker()
    private let action: (UInt32) -> Void
    private let signature: OSType = 0x4C756D61

    init(action: @escaping (UInt32) -> Void) { self.action = action }

    func start(mode: CaptureShortcut = .option) -> [String] {
        refs.forEach { UnregisterEventHotKey($0) }
        refs.removeAll()
        if let handler { RemoveEventHandler(handler); self.handler = nil }
        if let globalOptionMonitor { NSEvent.removeMonitor(globalOptionMonitor); self.globalOptionMonitor = nil }
        if let localOptionMonitor { NSEvent.removeMonitor(localOptionMonitor); self.localOptionMonitor = nil }
        optionTap = OptionTapTracker()
        guard mode != .disabled else { return [] }
        var unavailable: [String] = []
        if mode == .option {
            globalOptionMonitor = NSEvent.addGlobalMonitorForEvents(matching: .flagsChanged) { [weak self] event in
                self?.handleOption(event)
            }
            localOptionMonitor = NSEvent.addLocalMonitorForEvents(matching: .flagsChanged) { [weak self] event in
                self?.handleOption(event)
                return event
            }
            if globalOptionMonitor == nil { unavailable.append(mode.hoverLabel) }
        }
        var type = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
        let result = InstallEventHandler(GetApplicationEventTarget(), { _, event, user in
            guard let event, let user else { return OSStatus(eventNotHandledErr) }
            var hotkey = EventHotKeyID()
            let status = GetEventParameter(event, EventParamName(kEventParamDirectObject), EventParamType(typeEventHotKeyID),
                                           nil, MemoryLayout<EventHotKeyID>.size, nil, &hotkey)
            let owner = Unmanaged<Shortcuts>.fromOpaque(user).takeUnretainedValue()
            guard status == noErr, hotkey.signature == owner.signature else { return OSStatus(eventNotHandledErr) }
            owner.action(hotkey.id)
            return noErr
        }, 1, &type, Unmanaged.passUnretained(self).toOpaque(), &handler)
        guard result == noErr else { return unavailable + (mode == .option ? [mode.regionLabel] : [mode.hoverLabel, mode.regionLabel]) }
        for (id, key, label) in [(1, kVK_ANSI_T, mode.hoverLabel), (2, kVK_ANSI_R, mode.regionLabel)] {
            if mode == .option && id == 1 { continue }
            var ref: EventHotKeyRef?
            let modifiers = mode == .controlOption ? controlKey | optionKey : optionKey | shiftKey
            if RegisterEventHotKey(UInt32(key), UInt32(modifiers),
                                   EventHotKeyID(signature: signature, id: UInt32(id)),
                                   GetApplicationEventTarget(), 0, &ref) == noErr, let ref {
                refs.append(ref)
            } else { unavailable.append(label) }
        }
        return unavailable
    }

    private func handleOption(_ event: NSEvent) {
        let flags = event.modifierFlags
        let optionDown = flags.contains(.option)
        let forbidden: NSEvent.ModifierFlags = [.command, .shift, .control, .function]
        // A key may already be held before Option is pressed. Ignore modifier
        // keycodes here; their state is checked through flags/counters instead.
        let modifierKeys: Set<CGKeyCode> = [54, 55, 56, 57, 58, 59, 60, 61, 62, 63]
        let anotherKeyDown = optionDown && (0..<128).contains {
            let key = CGKeyCode($0)
            return !modifierKeys.contains(key) && CGEventSource.keyState(.combinedSessionState, key: key)
        }
        let pointerEvents: [CGEventType] = [.leftMouseDown, .rightMouseDown, .otherMouseDown, .scrollWheel,
                                           .leftMouseDragged, .rightMouseDragged, .otherMouseDragged]
        let pointer = pointerEvents.reduce(UInt32(0)) {
            $0 &+ CGEventSource.counterForEventType(.combinedSessionState, eventType: $1)
        }
        let clickHeld = CGEventSource.buttonState(.combinedSessionState, button: .left)
            || CGEventSource.buttonState(.combinedSessionState, button: .right)
            || CGEventSource.buttonState(.combinedSessionState, button: .center)
        if optionTap.update(optionDown: optionDown,
                            blocked: !flags.intersection(forbidden).isEmpty || anotherKeyDown || clickHeld,
                            time: event.timestamp,
                            keys: CGEventSource.counterForEventType(.combinedSessionState, eventType: .keyDown),
                            pointer: pointer,
                            modifiers: CGEventSource.counterForEventType(.combinedSessionState, eventType: .flagsChanged)) {
            action(1)
        }
    }

    deinit {
        refs.forEach { UnregisterEventHotKey($0) }
        if let handler { RemoveEventHandler(handler) }
        if let globalOptionMonitor { NSEvent.removeMonitor(globalOptionMonitor) }
        if let localOptionMonitor { NSEvent.removeMonitor(localOptionMonitor) }
    }
}
