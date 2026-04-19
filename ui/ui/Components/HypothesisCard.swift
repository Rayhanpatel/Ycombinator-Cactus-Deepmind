import SwiftUI

struct HypothesisCard: View {
    let hypothesis: MockHypothesis

    @State private var animatedProgress: CGFloat = 0

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .center, spacing: 12) {
                Label("Top hypothesis", systemImage: "sparkles.rectangle.stack")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(AppTheme.mist.opacity(0.65))

                Spacer()

                // Confidence arc
                ZStack {
                    Circle()
                        .stroke(Color.white.opacity(0.08), lineWidth: 3)
                        .frame(width: 40, height: 40)

                    Circle()
                        .trim(from: 0, to: animatedProgress)
                        .stroke(
                            confidenceColor,
                            style: StrokeStyle(lineWidth: 3, lineCap: .round)
                        )
                        .frame(width: 40, height: 40)
                        .rotationEffect(.degrees(-90))

                    Text("\(hypothesis.confidence)")
                        .font(.system(size: 13, weight: .heavy, design: .rounded))
                        .foregroundStyle(confidenceColor)
                }
            }

            Text(hypothesis.title)
                .font(.system(.title3, design: .rounded, weight: .bold))
                .foregroundStyle(.white)
                .lineLimit(2)

            Text(hypothesis.rationale)
                .font(.subheadline.weight(.medium))
                .foregroundStyle(AppTheme.mist.opacity(0.85))
                .lineLimit(3)
                .fixedSize(horizontal: false, vertical: true)

            // Next step with accent line
            HStack(alignment: .top, spacing: 10) {
                RoundedRectangle(cornerRadius: 1)
                    .fill(AppTheme.caution)
                    .frame(width: 3)
                    .frame(minHeight: 20)

                Text(hypothesis.nextStep)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.white.opacity(0.92))
                    .lineLimit(3)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(10)
            .background(AppTheme.caution.opacity(0.08), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        }
        .padding(16)
        .glassCard(cornerRadius: 24, fill: Color.black.opacity(0.38))
        .frame(maxWidth: .infinity, alignment: .leading)
        .onAppear {
            withAnimation(.easeOut(duration: 0.9).delay(0.2)) {
                animatedProgress = CGFloat(hypothesis.confidence) / 100.0
            }
        }
    }

    private var confidenceColor: Color {
        if hypothesis.confidence >= 80 {
            return AppTheme.success
        } else if hypothesis.confidence >= 50 {
            return AppTheme.caution
        } else {
            return AppTheme.steel
        }
    }
}

#Preview {
    ZStack {
        AppTheme.night.ignoresSafeArea()
        HypothesisCard(hypothesis: MockHypothesis(
            title: "Failed run capacitor",
            confidence: 87,
            rationale: "Clicking before shutoff plus intermittent cooling strongly matches prior Carrier capacitor failures.",
            nextStep: "Meter the capacitor and compare against the 45 µF rated value."
        ))
        .padding()
    }
}
