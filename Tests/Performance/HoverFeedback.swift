import SwiftUI

@MainActor extension App {
    func checkHoverFeedback(sample: (String) -> CGPoint, sentence: String, notebook: Notebook, selectArea: (CGRect) -> Void) async throws {
        let timeout = Task {
            try await Task.sleep(nanoseconds: 45_000_000_000)
            FileHandle.standardError.write(Data("Hover feedback check timed out.\n".utf8))
            exit(2)
        }
        defer { timeout.cancel() }
        func check(_ condition: Bool, _ label: String) throws {
            if !condition { throw NSError(domain: "HoverFixture", code: 1, userInfo: [NSLocalizedDescriptionKey: label]) }
        }
        func snapshot(_ name: String) throws {
            guard let directory = ProcessInfo.processInfo.environment["WAX_HOVER_IMAGES"] else { return }
            guard let view = panel?.contentView, let image = view.bitmapImageRepForCachingDisplay(in: view.bounds) else {
                throw CocoaError(.fileWriteUnknown)
            }
            view.layoutSubtreeIfNeeded()
            view.displayIfNeeded()
            view.cacheDisplay(in: view.bounds, to: image)
            guard let png = image.representation(using: .png, properties: [:]) else { throw CocoaError(.fileWriteUnknown) }
            try png.write(to: URL(fileURLWithPath: directory).appendingPathComponent(name + ".png"))
        }
        let word = sample("out")
        hover(at: word)
        guard let waiting = panel, waiting.isVisible, waiting.contentView is NSHostingView<PendingLookupCard> else {
            throw NSError(domain: "HoverFixture", code: 1, userInfo: [NSLocalizedDescriptionKey: "missing visible pending card"])
        }
        try check(notebook.recent.isEmpty, "pending card recorded a lookup")
        try snapshot("pending")
        // Cover the actual sample with both kinds of transient UI throughout the capture.
        waiting.setFrameOrigin(NSPoint(x: word.x - 100, y: word.y - waiting.frame.height / 2))
        let mask = SelectionPanel(contentRect: waiting.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        mask.backgroundColor = .black
        mask.level = .screenSaver
        mask.orderFrontRegardless()
        await job?.value
        mask.orderOut(nil)
        let shown = (panel?.contentView as? NSHostingView<ResultCard>)?.rootView.passage
        try check(panel === waiting && shown?.text == "rule out" && shown?.context == sentence, "word or window changed")
        let deadline = LookupTrace.now + 12
        while notebook.recent.first?.meaning.contains("排除") != true, LookupTrace.now < deadline {
            try await Task.sleep(nanoseconds: 50_000_000)
        }
        try check(notebook.recent.first?.meaning.contains("排除") == true, "local translation did not finish")
        try snapshot("result")

        hover(at: sample("out"))
        let superseded = job
        try await Task.sleep(nanoseconds: 80_000_000)
        hover(at: sample("results"))
        let replacement = panel
        await superseded?.value
        await job?.value
        try check(panel === replacement, "superseded window appeared")
        try check((panel?.contentView as? NSHostingView<ResultCard>)?.rootView.passage.text == "results", "replacement did not show results")
        hover(at: sample("out"))
        let cancelled = job
        try await Task.sleep(nanoseconds: 80_000_000)
        (panel?.contentView as? NSHostingView<PendingLookupCard>)?.rootView.close()
        await cancelled?.value
        try check(panel == nil, "closed lookup reappeared")
        let other = sample("results")
        selectArea(CGRect(x: other.x - 55, y: other.y - 20, width: sample("out").x - other.x + 110, height: 40))
        await job?.value
        let region = (panel?.contentView as? NSHostingView<ResultCard>)?.rootView.passage
        try check(region?.context == "" && region?.text.contains("rule out") == true, "region capture contained the selection overlay")
        let blank = sample("out")
        hover(at: CGPoint(x: blank.x, y: blank.y + 65))
        let empty = panel
        await job?.value
        try check(empty?.isVisible == true && panel === empty && !(panel?.contentView is NSHostingView<ResultCard>) && !(panel?.contentView is NSHostingView<PendingLookupCard>), "empty capture did not display its error")
    }
}
