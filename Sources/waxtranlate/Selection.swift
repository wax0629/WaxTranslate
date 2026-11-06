import AppKit

final class SelectionPanel: NSPanel {
    override var canBecomeKey: Bool { true }
}

final class SelectionView: NSView {
    var finish: (CGRect?) -> Void = { _ in }
    private var start: CGPoint?
    private var current: CGPoint?

    override var acceptsFirstResponder: Bool { true }
    override func resetCursorRects() { addCursorRect(bounds, cursor: .crosshair) }
    override func mouseDown(with event: NSEvent) {
        start = convert(event.locationInWindow, from: nil)
        current = start
        needsDisplay = true
    }
    override func mouseDragged(with event: NSEvent) {
        current = convert(event.locationInWindow, from: nil)
        needsDisplay = true
    }
    override func mouseUp(with event: NSEvent) {
        current = convert(event.locationInWindow, from: nil)
        guard let rect = selection, rect.width > 5, rect.height > 5, let window else { finish(nil); return }
        finish(window.convertToScreen(convert(rect, to: nil)))
    }
    override func keyDown(with event: NSEvent) {
        if event.keyCode == 53 { finish(nil) } else { super.keyDown(with: event) }
    }
    override func rightMouseDown(with event: NSEvent) { finish(nil) }

    private var selection: CGRect? {
        guard let start, let current else { return nil }
        return CGRect(x: min(start.x, current.x), y: min(start.y, current.y),
                      width: abs(start.x-current.x), height: abs(start.y-current.y)).intersection(bounds)
    }
    override func draw(_ dirtyRect: NSRect) {
        NSColor.black.withAlphaComponent(0.19).setFill()
        bounds.fill()
        if let rect = selection {
            rect.fill(using: .clear)
            NSColor.white.setStroke()
            NSBezierPath(rect: rect).stroke()
        }
    }
}
