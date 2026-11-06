import Carbon
import AppKit

final class Shortcuts {
    private var refs: [EventHotKeyRef] = []
    private var handler: EventHandlerRef?
    private let action: (UInt32) -> Void
    private let signature: OSType = 0x4C756D61

    init(action: @escaping (UInt32) -> Void) { self.action = action }

    func start() -> [String] {
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
        guard result == noErr else { return ["⌥⇧T", "⌥⇧R"] }
        var unavailable: [String] = []
        for (id, key, label) in [(1, kVK_ANSI_T, "⌥⇧T"), (2, kVK_ANSI_R, "⌥⇧R")] {
            var ref: EventHotKeyRef?
            if RegisterEventHotKey(UInt32(key), UInt32(optionKey | shiftKey),
                                   EventHotKeyID(signature: signature, id: UInt32(id)),
                                   GetApplicationEventTarget(), 0, &ref) == noErr, let ref {
                refs.append(ref)
            } else { unavailable.append(label) }
        }
        return unavailable
    }

    deinit {
        refs.forEach { UnregisterEventHotKey($0) }
        if let handler { RemoveEventHandler(handler) }
    }
}
