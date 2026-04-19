import SwiftUI

struct HypothesisCard: View {
    let hypothesis: MockHypothesis

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Label("Top hypothesis", systemImage: "sparkles.rectangle.stack")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(AppTheme.mist.opacity(0.72))
                Spacer()
                Text("\(hypothesis.confidence)%")
                    .font(.headline.weight(.heavy))
                    .foregroundStyle(AppTheme.accent)
            }

            Text(hypothesis.title)
                .font(.system(.title2, design: .rounded, weight: .bold))
                .foregroundStyle(.white)
                .lineLimit(2)

            Text(hypothesis.rationale)
                .font(.subheadline.weight(.medium))
                .foregroundStyle(AppTheme.mist)
                .lineLimit(3)
                .fixedSize(horizontal: false, vertical: true)

            HStack(alignment: .top, spacing: 10) {
                Image(systemName: "arrow.turn.down.right")
                    .foregroundStyle(AppTheme.caution)
                Text(hypothesis.nextStep)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.white)
                    .lineLimit(3)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(16)
        .glassCard(cornerRadius: 28, fill: Color.black.opacity(0.34))
        .frame(maxWidth: 360, alignment: .leading)
    }
}

#Preview {
    ZStack {
        AppTheme.cameraGradient.ignoresSafeArea()
        HypothesisCard(hypothesis: PreviewScenarios.initial.hypothesis!)
            .padding()
    }
}
