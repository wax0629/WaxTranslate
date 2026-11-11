import AppKit
import SwiftUI

private final class ReferenceProtocol: URLProtocol {
    private static let lock = NSLock()
    private static var requests: [URLRequest] = []
    static var offline = false
    static var status = 200
    static var captured: [URLRequest] { lock.lock(); defer { lock.unlock() }; return requests }
    override class func canInit(with request: URLRequest) -> Bool { request.url?.host == "www.wikidata.org" }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.lock.lock(); Self.requests.append(request); Self.lock.unlock()
        if Self.offline { client?.urlProtocol(self, didFailWithError: URLError(.notConnectedToInternet)); return }
        let response = HTTPURLResponse(url: request.url!, statusCode: Self.status, httpVersion: nil, headerFields: nil)!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(#"{"search":[{"id":"Q123","description":"测试名称参考","match":{"text":"UnknownSDK"}}]}"#.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@MainActor enum ReferenceTests {
    static func run() async throws {
        guard URLProtocol.registerClass(ReferenceProtocol.self) else { fatalError("Cannot intercept references") }
        defer { URLProtocol.unregisterClass(ReferenceProtocol.self) }
        let suite = "WaxTranslate.Test.references." + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        // An old automatic-reference preference must never opt the reader into
        // a network request when the real SwiftUI card mounts.
        for oldSetting in [true, false] {
            defaults.set(oldSetting, forKey: "lookup.onlineReferences")
            let card = ResultCard(passage: Passage(text: "UnknownSDK", context: "We used UnknownSDK in this private sentence.", language: "en", structure: .code),
                                  notebook: Notebook(defaults: defaults), preferences: Preferences(defaults: defaults), close: {}, speak: { _, _ in }, focusForDownload: {})
            let window = NSWindow(contentRect: CGRect(x: -20000, y: -20000, width: 365, height: 600), styleMask: [.borderless], backing: .buffered, defer: false)
            window.isReleasedWhenClosed = false
            window.contentView = NSHostingView(rootView: card)
            window.orderFrontRegardless()
            try await Task.sleep(nanoseconds: 200_000_000)
            window.contentView = nil; window.close()
            guard ReferenceProtocol.captured.isEmpty else { fatalError("Card automatically sent a reference request") }
        }
        let book = Notebook(defaults: defaults)
        let region = Passage(text: "The sample contains a green triangle.", context: "", language: "en")
        let bank = Passage(text: "bank", context: "They sat on the river bank.", language: "en")
        for (passage, result) in [(region, LookupResult(meaning: "样本包含一个绿色的三角形。", origin: .region)),
                                  (bank, LookupResult(meaning: "", origin: .unresolved, sentenceTranslation: "他们坐在河岸上。", wordReference: "银行"))] {
            let card = ResultCard(passage: passage, notebook: book, preferences: Preferences(defaults: defaults), initialResult: result, close: {}, speak: { _, _ in }, focusForDownload: {})
            let window = NSWindow(contentRect: CGRect(x: -20000, y: -20000, width: 365, height: 600), styleMask: [.borderless], backing: .buffered, defer: false)
            window.isReleasedWhenClosed = false
            window.contentView = NSHostingView(rootView: card)
            window.orderFrontRegardless()
            try await Task.sleep(nanoseconds: 200_000_000)
            window.contentView = nil; window.close()
        }
        guard book.totalLookups == 0, book.recent.isEmpty, book.entries.isEmpty else { fatalError("Card recorded region or unconfirmed meaning") }
        print("Passed: mounted native region and unconfirmed cards do not write notebook activity.")
        let confirmed = ResultCard(passage: bank, notebook: book, preferences: Preferences(defaults: defaults),
                                   initialResult: LookupResult(meaning: "河岸", origin: .sentence, sentenceTranslation: "他们坐在河岸上。"), close: {}, speak: { _, _ in }, focusForDownload: {})
        let confirmedWindow = NSWindow(contentRect: CGRect(x: -20000, y: -20000, width: 365, height: 600), styleMask: [.borderless], backing: .buffered, defer: false)
        confirmedWindow.isReleasedWhenClosed = false
        confirmedWindow.contentView = NSHostingView(rootView: confirmed)
        confirmedWindow.orderFrontRegardless()
        try await Task.sleep(nanoseconds: 200_000_000)
        confirmedWindow.contentView = nil; confirmedWindow.close()
        guard book.totalLookups == 1, book.recent.first?.meaning == "河岸" else { fatalError("Confirmed card did not record the recovered meaning") }
        print("Passed: mounted confirmed card records the recovered contextual meaning.")
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [ReferenceProtocol.self]
        let session = URLSession(configuration: configuration)
        defer { session.invalidateAndCancel() }
        ReferenceProtocol.offline = true
        do { _ = try await WordReferences.search("UnknownSDK", session: session); fatalError("Offline call succeeded") }
        catch let error as URLError { guard error.code == .notConnectedToInternet else { throw error } }
        ReferenceProtocol.offline = false
        let found = try await WordReferences.search("UnknownSDK", session: session)
        guard found.count == 1, found[0].id == "Q123" else { fatalError("Manual retry did not recover") }
        ReferenceProtocol.status = 503
        do { _ = try await WordReferences.search("UnknownSDK", session: session); fatalError("HTTP failure was accepted") }
        catch let error as URLError { guard error.code == .badServerResponse else { throw error } }
        guard ReferenceProtocol.captured.count == 3 else { fatalError("Unexpected request count") }
        for request in ReferenceProtocol.captured {
            let query = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)!.queryItems!
            guard query.first(where: { $0.name == "search" })?.value == "UnknownSDK", request.httpBody == nil,
                  !request.url!.absoluteString.contains("private"),
                  Set(query.map(\.name)) == Set(["action", "search", "language", "uselang", "type", "limit", "format"]) else { fatalError("Request includes context or unexpected fields") }
        }
        print("Passed: real card sends no automatic reference requests with either legacy preference; word-only manual request, offline retry and HTTP failure (intercepted, no network).")
    }
}
