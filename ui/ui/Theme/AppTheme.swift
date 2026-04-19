import SwiftUI

enum AppTheme {
    // MARK: - Core palette
    static let night = Color(red: 0.06, green: 0.08, blue: 0.11)
    static let graphite = Color(red: 0.12, green: 0.15, blue: 0.19)
    static let steel = Color(red: 0.26, green: 0.34, blue: 0.42)
    static let mist = Color.white.opacity(0.85)

    static let accent = Color(red: 0.20, green: 0.84, blue: 0.70)
    static let listening = Color(red: 0.10, green: 0.72, blue: 0.96)
    static let caution = Color(red: 0.98, green: 0.71, blue: 0.26)
    static let danger = Color(red: 0.96, green: 0.34, blue: 0.30)
    static let success = Color(red: 0.34, green: 0.86, blue: 0.50)

    static let border = Color.white.opacity(0.12)
    static let borderSubtle = Color.white.opacity(0.06)
    static let panelFill = Color.black.opacity(0.32)
    static let panelFillStrong = Color.black.opacity(0.48)
    static let shadow = Color.black.opacity(0.32)

    // MARK: - Gradients
    static var cameraGradient: LinearGradient {
        LinearGradient(
            colors: [
                Color(red: 0.05, green: 0.07, blue: 0.10),
                Color(red: 0.10, green: 0.13, blue: 0.18),
                Color(red: 0.18, green: 0.24, blue: 0.30)
            ],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    }

    static var overlayGradient: LinearGradient {
        LinearGradient(
            colors: [
                Color.black.opacity(0.22),
                Color.black.opacity(0.04),
                Color.black.opacity(0.58)
            ],
            startPoint: .top,
            endPoint: .bottom
        )
    }

    // MARK: - Stage-based vignette color
    static func vignetteColor(for stage: SessionStage) -> Color {
        switch stage {
        case .idle:
            return accent.opacity(0.06)
        case .listening:
            return listening.opacity(0.10)
        case .assistantResponding:
            return accent.opacity(0.08)
        case .safetyAlert:
            return danger.opacity(0.14)
        case .closeJobReview:
            return success.opacity(0.08)
        }
    }
}

// MARK: - Glass card modifier

private struct GlassCardModifier: ViewModifier {
    let cornerRadius: CGFloat
    let fill: Color
    let borderColor: Color

    func body(content: Content) -> some View {
        content
            .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: cornerRadius, style: .continuous))
            .background(fill, in: RoundedRectangle(cornerRadius: cornerRadius, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .stroke(borderColor, lineWidth: 0.75)
            )
            .shadow(color: AppTheme.shadow, radius: 20, x: 0, y: 10)
    }
}

extension View {
    func glassCard(cornerRadius: CGFloat = 24, fill: Color = AppTheme.panelFill, border: Color = AppTheme.border) -> some View {
        modifier(GlassCardModifier(cornerRadius: cornerRadius, fill: fill, borderColor: border))
    }
}
