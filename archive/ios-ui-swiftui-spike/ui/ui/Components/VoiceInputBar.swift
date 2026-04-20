import SwiftUI

struct VoiceInputBar: View {
    let stage: SessionStage
    let onCloseJobTap: () -> Void

    @State private var isPulsing = false

    var body: some View {
        HStack(alignment: .center, spacing: 14) {
            // Status text + waveform
            HStack(spacing: 8) {
                AnimatedWaveform(active: stage == .listening || stage == .assistantResponding, tint: stageTint)
                VStack(alignment: .leading, spacing: 2) {
                    Text(statusTitle)
                        .font(.caption.weight(.bold))
                        .foregroundStyle(.white)
                    Text(statusSubtitle)
                        .font(.caption2.weight(.medium))
                        .foregroundStyle(AppTheme.mist.opacity(0.5))
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            // Mic button (center, prominent)
            ZStack {
                // Pulse ring
                Circle()
                    .stroke(stageTint.opacity(0.15), lineWidth: 1.5)
                    .frame(width: 62, height: 62)
                    .scaleEffect(isPulsing ? 1.2 : 1.0)
                    .opacity(isPulsing ? 0.0 : 0.5)

                Circle()
                    .fill(
                        RadialGradient(
                            colors: [stageTint, stageTint.opacity(0.7)],
                            center: .center,
                            startRadius: 0,
                            endRadius: 26
                        )
                    )
                    .frame(width: 52, height: 52)
                    .overlay(
                        Image(systemName: micIcon)
                            .font(.system(size: 20, weight: .bold))
                            .foregroundStyle(.white)
                            .contentTransition(.symbolEffect(.replace))
                    )
                    .shadow(color: stageTint.opacity(0.35), radius: 12, x: 0, y: 4)
            }

            // Close Job button
            Button(action: onCloseJobTap) {
                HStack(spacing: 6) {
                    Image(systemName: "doc.text.fill")
                        .font(.system(size: 12, weight: .bold))
                    Text("Close")
                        .font(.caption.weight(.bold))
                }
                .foregroundStyle(.white.opacity(0.8))
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .stroke(AppTheme.borderSubtle, lineWidth: 0.75)
                )
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(
            AppTheme.night
                .overlay(
                    LinearGradient(
                        colors: [Color.white.opacity(0.04), Color.clear],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                )
        )
        .onAppear {
            withAnimation(.easeInOut(duration: 1.6).repeatForever(autoreverses: false)) {
                isPulsing = true
            }
        }
    }

    private var stageTint: Color {
        switch stage {
        case .idle: AppTheme.accent
        case .listening: AppTheme.listening
        case .assistantResponding: AppTheme.accent
        case .safetyAlert: AppTheme.danger
        case .closeJobReview: AppTheme.success
        }
    }

    private var micIcon: String {
        switch stage {
        case .idle: "mic.fill"
        case .listening: "waveform"
        case .assistantResponding: "sparkles"
        case .safetyAlert: "exclamationmark.triangle.fill"
        case .closeJobReview: "checkmark.circle.fill"
        }
    }

    private var statusTitle: String {
        switch stage {
        case .idle: "Ready"
        case .listening: "Listening..."
        case .assistantResponding: "Thinking"
        case .safetyAlert: "Safety stop"
        case .closeJobReview: "Review ready"
        }
    }

    private var statusSubtitle: String {
        switch stage {
        case .idle: "Tap mic to describe the issue"
        case .listening: "Hold steady on the unit"
        case .assistantResponding: "Analyzing symptom + camera"
        case .safetyAlert: "Action required"
        case .closeJobReview: "Tap Close to review & export"
        }
    }
}

// MARK: - Animated waveform

struct AnimatedWaveform: View {
    let active: Bool
    let tint: Color

    private let barCount = 7

    var body: some View {
        HStack(alignment: .center, spacing: 2.5) {
            ForEach(0..<barCount, id: \.self) { index in
                Capsule(style: .continuous)
                    .fill(active ? tint : AppTheme.steel.opacity(0.35))
                    .frame(width: 3, height: barHeight(for: index))
                    .animation(
                        active
                            ? .easeInOut(duration: 0.35 + Double(index) * 0.07)
                                .repeatForever(autoreverses: true)
                                .delay(Double(index) * 0.05)
                            : .default,
                        value: active
                    )
            }
        }
        .frame(width: 32, height: 18)
    }

    private func barHeight(for index: Int) -> CGFloat {
        let heights: [CGFloat] = active
            ? [8, 15, 11, 18, 13, 16, 9]
            : [4, 6, 4, 7, 5, 6, 4]
        return heights[index % heights.count]
    }
}

#Preview {
    VStack {
        Spacer()
        VoiceInputBar(stage: .listening, onCloseJobTap: {})
    }
    .background(AppTheme.night.ignoresSafeArea())
}
