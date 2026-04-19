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

            Text(hypothesis.rationale)
                .font(.subheadline.weight(.medium))
                .foregroundStyle(AppTheme.mist)
                .fixedSize(horizontal: false, vertical: true)

            HStack(alignment: .top, spacing: 10) {
                Image(systemName: "arrow.turn.down.right")
                    .foregroundStyle(AppTheme.caution)
                Text(hypothesis.nextStep)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.white)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(18)
        .glassCard(cornerRadius: 28, fill: Color.black.opacity(0.34))
    }
}

#Preview {
    ZStack {
        AppTheme.cameraGradient.ignoresSafeArea()
        HypothesisCard(hypothesis: PreviewScenarios.initial.hypothesis!)
            .padding()
    }
}
