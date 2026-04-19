import SwiftUI

struct TalkButton: View {
    let stage: SessionStage

    var body: some View {
        VStack(spacing: 8) {
            ZStack {
                Circle()
                    .fill(coreColor.opacity(0.18))
                    .frame(width: 88, height: 88)

                Circle()
                    .fill(coreColor)
                    .frame(width: 70, height: 70)
                    .overlay(
                        Image(systemName: iconName)
                            .font(.system(size: 24, weight: .bold))
                            .foregroundStyle(.white)
                    )
            }

            VStack(spacing: 2) {
                Text(title)
                    .font(.subheadline.weight(.bold))
                    .foregroundStyle(.white)
                Text(subtitle)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(AppTheme.mist.opacity(0.72))
                    .multilineTextAlignment(.center)
            }
        }
    }

    private var coreColor: Color {
        switch stage {
        case .idle:
            AppTheme.accent
        case .listening:
            AppTheme.listening
        case .assistantResponding:
            AppTheme.caution
        case .safetyAlert:
            AppTheme.danger
        case .closeJobReview:
            AppTheme.success
        }
    }

    private var iconName: String {
        switch stage {
        case .idle:
            "mic.fill"
        case .listening:
            "waveform"
        case .assistantResponding:
            "sparkles"
        case .safetyAlert:
            "exclamationmark.triangle.fill"
        case .closeJobReview:
            "checkmark.bubble.fill"
        }
    }

    private var title: String {
        switch stage {
        case .idle:
            "Tap to talk"
        case .listening:
            "Listening"
        case .assistantResponding:
            "Analyzing"
        case .safetyAlert:
            "Safety stop"
        case .closeJobReview:
            "Review ready"
        }
    }

    private var subtitle: String {
        switch stage {
        case .idle:
            "Mic capture comes next"
        case .listening:
            "Hold steady on the unit"
        case .assistantResponding:
            "Streaming response mock"
        case .safetyAlert:
            "UI interrupt state"
        case .closeJobReview:
            "Open the summary sheet"
        }
    }
}

#Preview {
    ZStack {
        AppTheme.cameraGradient.ignoresSafeArea()
        TalkButton(stage: .assistantResponding)
    }
}
