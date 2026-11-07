import SwiftUI

enum DeskTheme {
    static let paper = adaptive(0xf8f7f2, 0x1a211e)
    static let sheet = adaptive(0xfffefa, 0x242d28)
    static let ink = adaptive(0x202c28, 0xf7f6ed)
    static let muted = adaptive(0x58645e, 0xb3beb6)
    static let rule = adaptive(0xd7dad2, 0x46504a)
    static let accent = adaptive(0xac442d, 0xffa58a)
    static let soft = adaptive(0xeceee7, 0x313d36)
    static let coverInk = Color(red: 0.12, green: 0.17, blue: 0.15)

    private static func adaptive(_ light: Int, _ dark: Int) -> Color {
        Color(nsColor: NSColor(name: nil) { appearance in
            let rgb = appearance.bestMatch(from: [.aqua, .darkAqua]) == .darkAqua ? dark : light
            return NSColor(srgbRed: CGFloat(rgb >> 16) / 255, green: CGFloat(rgb >> 8 & 255) / 255,
                           blue: CGFloat(rgb & 255) / 255, alpha: 1)
        })
    }
}

struct BookRule: View {
    @Environment(\.displayScale) private var scale

    var body: some View {
        Rectangle().fill(DeskTheme.rule).frame(height: 1 / scale).accessibilityHidden(true)
    }
}

struct RiverCover: View {
    // Installed apps carry the photograph inside the signed bundle. A source
    // build reads the same master used to assemble it.
    private static let image: NSImage? = {
        if Bundle.main.bundleURL.pathExtension == "app" {
            return Bundle.main.url(forResource: "river", withExtension: "jpg").flatMap(NSImage.init(contentsOf:))
        }
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
        return NSImage(contentsOf: root.appendingPathComponent("Assets/Editorial/river.jpg"))
    }()

    var body: some View {
        GeometryReader { proxy in
            ZStack {
                DeskTheme.coverInk
                if let image = Self.image {
                    Image(nsImage: image).resizable().scaledToFill()
                }
            }
            .frame(width: proxy.size.width, height: proxy.size.height)
            .clipped()
            .overlay {
                LinearGradient(stops: [
                    .init(color: .black.opacity(0.48), location: 0),
                    .init(color: .black.opacity(0.30), location: 0.43),
                    .init(color: .clear, location: 0.78)
                ], startPoint: .leading, endPoint: .trailing)
            }
        }.allowsHitTesting(false).accessibilityHidden(true)
    }
}

struct ReaderActionStyle: ButtonStyle {
    @Environment(\.isEnabled) private var enabled
    var emphasized = false

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 12, weight: .semibold))
            .padding(.horizontal, 13).frame(minHeight: 31)
            .foregroundStyle(emphasized ? DeskTheme.paper : DeskTheme.ink)
            .background(emphasized ? DeskTheme.ink : DeskTheme.soft, in: Capsule())
            .opacity(enabled ? (configuration.isPressed ? 0.7 : 1) : 0.44)
    }
}
