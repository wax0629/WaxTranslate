import AppKit
import ApplicationServices

// Exercises only the specific test process's accessibility tree. It never types
// into the frontmost app or reads any other window.
func attribute(_ node: AXUIElement, _ name: CFString) -> CFTypeRef? {
    var value: CFTypeRef?
    return AXUIElementCopyAttributeValue(node, name, &value) == .success ? value : nil
}
func string(_ node: AXUIElement, _ name: String) -> String {
    attribute(node, name as CFString) as? String ?? ""
}
func find(_ node: AXUIElement, depth: Int = 0, where matches: (AXUIElement) -> Bool) -> AXUIElement? {
    if matches(node) { return node }
    guard depth < 16, let children = attribute(node, kAXChildrenAttribute as CFString) as? [AXUIElement] else { return nil }
    for child in children { if let value = find(child, depth: depth + 1, where: matches) { return value } }
    return nil
}
func wait(_ label: String, for predicate: () -> AXUIElement?) throws -> AXUIElement {
    let deadline = Date().addingTimeInterval(45)
    repeat {
        if let node = predicate() { return node }
        Thread.sleep(forTimeInterval: 0.12)
    } while Date() < deadline
    throw NSError(domain: "OfflineInstall", code: 1, userInfo: [NSLocalizedDescriptionKey: "Timed out: " + label])
}
func press(_ button: AXUIElement) throws {
    guard AXUIElementPerformAction(button, kAXPressAction as CFString) == .success else { throw CocoaError(.userCancelled) }
}
func named(_ node: AXUIElement, _ name: String) -> Bool {
    [kAXTitleAttribute, kAXDescriptionAttribute, kAXValueAttribute].contains { string(node, $0) == name }
}

let pid = pid_t(CommandLine.arguments[1])!
let app = AXUIElementCreateApplication(pid)
guard AXIsProcessTrusted() else { fatalError("This GUI test needs an Accessibility-enabled test runner.") }
let reading = try wait("reading navigation at first launch") {
    find(app) { string($0, kAXRoleAttribute) == kAXButtonRole && named($0, "对照翻译") }
}
try press(reading)
let editor = try wait("reading editor") { find(app) { string($0, kAXRoleAttribute) == kAXTextAreaRole } }
for (source, expected) in [("Thank you.", "谢"), ("谢谢你。", "thank")] {
    guard AXUIElementSetAttributeValue(editor, kAXValueAttribute as CFString, source as CFString) == .success else {
        throw CocoaError(.fileWriteNoPermission)
    }
    let button = try wait("enabled translate button") {
        find(app) { string($0, kAXRoleAttribute) == kAXButtonRole && named($0, "翻译全文")
                    && attribute($0, kAXEnabledAttribute as CFString) as? Bool == true }
    }
    try press(button)
    let result = try wait("translation of " + source) {
        find(app) { node in
            string(node, kAXRoleAttribute) == kAXStaticTextRole &&
            [kAXValueAttribute, kAXDescriptionAttribute].contains { string(node, $0).lowercased().contains(expected) }
        }
    }
    let text = [string(result, kAXValueAttribute), string(result, kAXDescriptionAttribute)].first { !$0.isEmpty } ?? ""
    guard !text.contains("▁") else { fatalError("Tokenizer markup is visible in the reading page") }
    print("\(source) → \(text)")
}
