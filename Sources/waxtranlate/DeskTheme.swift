import SwiftUI

/// Warm paper in daylight and a low-luminance reading surface in Dark Mode.
enum DeskTheme {
    static let paper = adaptive(0xf6ecd6, 0x302822)
    static let sheet = adaptive(0xfcf5e4, 0x392f28)
    static let ink = adaptive(0x392a22, 0xf4e8d1)
    static let muted = adaptive(0x6b5746, 0xcbbb9f)
    static let rule = adaptive(0xc3ac87, 0x79644d)
    static let wax = adaptive(0x803c34, 0xe9aa96)
    static let binding = Color(red: 0.46, green: 0.21, blue: 0.18)
    static let gilt = Color(red: 0.84, green: 0.73, blue: 0.55)
    static let ivory = Color(red: 1, green: 0.95, blue: 0.84)

    private static func adaptive(_ light: Int, _ dark: Int) -> Color {
        Color(nsColor: NSColor(name: nil) { appearance in
            let rgb = appearance.bestMatch(from: [.aqua, .darkAqua]) == .darkAqua ? dark : light
            return NSColor(srgbRed: CGFloat(rgb >> 16) / 255, green: CGFloat(rgb >> 8 & 255) / 255,
                           blue: CGFloat(rgb & 255) / 255, alpha: 1)
        })
    }
}

struct WalnutGrain: View {
    var body: some View {
        Canvas { context, size in
            context.fill(Path(CGRect(origin: .zero, size: size)), with: .linearGradient(
                Gradient(colors: [Color(red: 0.23, green: 0.15, blue: 0.12),
                                  Color(red: 0.29, green: 0.20, blue: 0.15),
                                  Color(red: 0.21, green: 0.14, blue: 0.11)]),
                startPoint: .zero, endPoint: CGPoint(x: size.width, y: 0)))
            for x in stride(from: -8.0, to: size.width + 8, by: 2.6) {
                var grain = Path()
                for y in stride(from: 0.0, through: size.height + 12, by: 12) {
                    let bend = sin(y / 88 + x / 24) + 0.6 * sin(y / 47 + x / 38)
                    let p = CGPoint(x: x + 2 * bend, y: y)
                    if y == 0 { grain.move(to: p) } else { grain.addLine(to: p) }
                }
                context.stroke(grain, with: .color(.black.opacity(0.065 + 0.035 * sin(x))),
                               lineWidth: 1.2 + 0.5 * cos(x / 6))
            }
        }.accessibilityHidden(true).allowsHitTesting(false)
    }
}

struct BookRule: View {
    var body: some View {
        Rectangle().fill(DeskTheme.rule).frame(height: 1).accessibilityHidden(true)
    }
}
