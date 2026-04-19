import SwiftUI

struct TranscriptCard: View {
    let lines: [TranscriptLine]
    let stage: SessionStage
    let footer: String

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label("Transcript", systemImage: "captions.bubble")
                    .font(.headline.weight(.bold))
                    .foregroundStyle(.white)
                Spacer()
                Text(stage.rawValue)
                    .font(.caption.weight(.bold))
                    .foregroundStyle(stageTint)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(stageTint.opacity(0.18), in: Capsule())
            }

            VStack(alignment: .leading, spacing: 10) {
                ForEach(Array(lines.suffix(2))) { line in
                    HStack(alignment: .top, spacing: 10) {
                        Text(line.speaker.title)
                            .font(.caption.weight(.bold))
                            .foregroundStyle(line.speaker.tint)
                            .frame(width: 50, alignment: .leading)
                        Text(line.text)
                            .font(.subheadline.weight(.medium))
                            .foregroundStyle(AppTheme.mist)
                            .lineLimit(3)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }

            HStack(spacing: 12) {
                WaveformRow(active: stage == .listening)
                Text(footer)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(AppTheme.mist.opacity(0.72))
                    .lineLimit(1)
            }
        }
        .padding(16)
        .glassCard(cornerRadius: 26, fill: Color.black.opacity(0.38))
    }

    private var stageTint: Color {
        switch stage {
        case .idle:
            AppTheme.success
        case .listening:
            AppTheme.listening
        case .assistantResponding:
            AppTheme.accent
        case .safetyAlert:
            AppTheme.danger
        case .closeJobReview:
            AppTheme.caution
        }
    }
}

private struct WaveformRow: View {
    let active: Bool

    var body: some View {
        HStack(alignment: .bottom, spacing: 4) {
            ForEach(0..<6, id: \.self) { index in
                Capsule(style: .continuous)
                    .fill(active ? AppTheme.listening : AppTheme.steel.opacity(0.55))
                    .frame(width: 5, height: activeHeights[index])
            }
        }
        .frame(height: 18)
    }

    private let activeHeights: [CGFloat] = [8, 14, 11, 18, 12, 9]
}

#Preview {
    ZStack {
        AppTheme.cameraGradient.ignoresSafeArea()
        TranscriptCard(
            lines: PreviewScenarios.initial.transcriptLines,
            stage: PreviewScenarios.initial.stage,
            footer: PreviewScenarios.initial.transcriptFooter
        )
        .padding()
    }
}
