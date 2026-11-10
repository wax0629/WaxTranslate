import SwiftUI

enum DeskTheme {
    static let paper = adaptive(0xf8f7f3, 0x1d1e1d)
    static let sheet = adaptive(0xfffefa, 0x292b29)
    static let ink = adaptive(0x242523, 0xf7f6ed)
    static let muted = adaptive(0x5c605b, 0xbac0b8)
    static let rule = adaptive(0xd7d8d2, 0x4b5049)
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

struct MangaCover: View {
    private static let image: NSImage? = {
        if Bundle.main.bundleURL.pathExtension == "app" {
            return Bundle.main.url(forResource: "glance", withExtension: "png").flatMap(NSImage.init(contentsOf:))
        }
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
        return NSImage(contentsOf: root.appendingPathComponent("Assets/Editorial/glance.png"))
    }()

    var body: some View {
        GeometryReader { bounds in
            ZStack(alignment: .trailing) {
                DeskTheme.paper
                if let image = Self.image {
                    Image(nsImage: image).resizable().scaledToFill()
                        .frame(width: bounds.size.width * 0.72, height: bounds.size.height).clipped()
                }
                LinearGradient(stops: [.init(color: DeskTheme.paper, location: 0),
                    .init(color: DeskTheme.paper.opacity(0.97), location: 0.39),
                    .init(color: DeskTheme.paper.opacity(0.82), location: 0.55),
                    .init(color: DeskTheme.paper.opacity(bounds.size.width < 760 ? 0.88 : 0.12), location: 0.82)], startPoint: .leading, endPoint: .trailing)
            }.frame(width: bounds.size.width, height: bounds.size.height).clipped()
        }.allowsHitTesting(false).accessibilityHidden(true)
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
