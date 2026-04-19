import SwiftUI

struct SafetyBanner: View {
    let level: SafetyLevel
    let message: String

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: level == .stop ? "exclamationmark.shield.fill" : "shield.lefthalf.filled")
                .font(.system(size: 18, weight: .bold))
                .foregroundStyle(level.tint)

            VStack(alignment: .leading, spacing: 4) {
                Text(level == .stop ? "Safety interrupt" : "Safety watch")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(level.tint)
                Text(message)
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(.white)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Spacer(minLength: 0)
        }
        .padding(16)
        .glassCard(cornerRadius: 22, fill: Color.black.opacity(level == .stop ? 0.54 : 0.42))
        .overlay(
            RoundedRectangle(cornerRadius: 22, style: .continuous)
                .stroke(level.tint.opacity(0.55), lineWidth: 1)
        )
    }
}

#Preview {
    ZStack {
        AppTheme.cameraGradient.ignoresSafeArea()
        SafetyBanner(
            level: .stop,
            message: "Safety stop: exposed conductors near the disconnect. Kill power and verify lockout before touching the cabinet."
        )
        .padding()
    }
}
