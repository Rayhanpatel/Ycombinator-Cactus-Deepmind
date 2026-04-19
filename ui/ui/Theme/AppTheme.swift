import SwiftUI

enum AppTheme {
    static let night = Color(red: 0.07, green: 0.10, blue: 0.13)
    static let graphite = Color(red: 0.14, green: 0.18, blue: 0.22)
    static let steel = Color(red: 0.29, green: 0.38, blue: 0.45)
    static let mist = Color.white.opacity(0.82)

    static let accent = Color(red: 0.22, green: 0.82, blue: 0.68)
    static let listening = Color(red: 0.13, green: 0.79, blue: 0.93)
    static let caution = Color(red: 0.98, green: 0.71, blue: 0.26)
    static let danger = Color(red: 0.98, green: 0.38, blue: 0.34)
    static let success = Color(red: 0.38, green: 0.85, blue: 0.53)

    static let border = Color.white.opacity(0.14)
    static let panelFill = Color.black.opacity(0.28)
    static let panelFillStrong = Color.black.opacity(0.42)
    static let shadow = Color.black.opacity(0.28)

    static var cameraGradient: LinearGradient {
        LinearGradient(
            colors: [night, graphite, steel],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    }

    static var overlayGradient: LinearGradient {
        LinearGradient(
            colors: [
                Color.black.opacity(0.16),
                Color.black.opacity(0.08),
                Color.black.opacity(0.54)
            ],
            startPoint: .top,
            endPoint: .bottom
        )
    }
}

private struct GlassCardModifier: ViewModifier {
    let cornerRadius: CGFloat
    let fill: Color

    func body(content: Content) -> some View {
        content
            .background(fill, in: RoundedRectangle(cornerRadius: cornerRadius, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .stroke(AppTheme.border, lineWidth: 1)
            )
            .shadow(color: AppTheme.shadow, radius: 18, x: 0, y: 10)
    }
}

extension View {
    func glassCard(cornerRadius: CGFloat = 24, fill: Color = AppTheme.panelFill) -> some View {
        modifier(GlassCardModifier(cornerRadius: cornerRadius, fill: fill))
    }
}
