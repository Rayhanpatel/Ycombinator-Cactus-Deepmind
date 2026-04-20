import SwiftUI

struct SafetyBanner: View {
    let level: SafetyLevel
    let message: String

    @State private var borderPulse = false

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            // Icon with glow
            ZStack {
                if level == .stop {
                    Circle()
                        .fill(level.tint.opacity(0.2))
                        .frame(width: 36, height: 36)
                        .scaleEffect(borderPulse ? 1.3 : 1.0)
                        .opacity(borderPulse ? 0.0 : 0.5)
                }
                Image(systemName: level == .stop ? "exclamationmark.shield.fill" : "shield.lefthalf.filled")
                    .font(.system(size: 20, weight: .bold))
                    .foregroundStyle(level.tint)
            }
            .frame(width: 36, height: 36)

            VStack(alignment: .leading, spacing: 4) {
                Text(level == .stop ? "SAFETY INTERRUPT" : "SAFETY WATCH")
                    .font(.system(size: 11, weight: .heavy))
                    .tracking(1.0)
                    .foregroundStyle(level.tint)
                Text(message)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.white)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Spacer(minLength: 0)
        }
        .padding(16)
        .glassCard(
            cornerRadius: 20,
            fill: Color.black.opacity(level == .stop ? 0.56 : 0.42),
            border: level.tint.opacity(borderPulse ? 0.6 : 0.3)
        )
        .onAppear {
            guard level == .stop else { return }
            withAnimation(.easeInOut(duration: 1.0).repeatForever(autoreverses: true)) {
                borderPulse = true
            }
        }
    }
}

#Preview {
    ZStack {
        AppTheme.cameraGradient.ignoresSafeArea()
        VStack(spacing: 12) {
            SafetyBanner(
                level: .stop,
                message: "Safety stop: exposed conductors near the disconnect. Kill power and verify lockout before touching the cabinet."
            )
            SafetyBanner(
                level: .caution,
                message: "Capacitors may hold charge after power is disconnected."
            )
        }
        .padding()
    }
}
