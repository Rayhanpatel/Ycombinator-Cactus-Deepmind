import SwiftUI

struct TopStatusBar: View {
    let scenario: OnSiteScenario
    let onScenarioTap: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top, spacing: 12) {
                VStack(alignment: .leading, spacing: 6) {
                    Text(scenario.jobLabel.uppercased())
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(AppTheme.mist.opacity(0.72))
                    Text(scenario.equipmentLabel)
                        .font(.system(.title3, design: .rounded, weight: .bold))
                        .foregroundStyle(.white)
                        .lineLimit(1)
                        .minimumScaleFactor(0.82)
                }

                Spacer(minLength: 0)

                Button(action: onScenarioTap) {
                    Image(systemName: "slider.horizontal.3")
                        .font(.system(size: 15, weight: .bold))
                        .foregroundStyle(.white)
                        .frame(width: 38, height: 38)
                        .background(AppTheme.panelFillStrong, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                        .overlay(
                            RoundedRectangle(cornerRadius: 14, style: .continuous)
                                .stroke(AppTheme.border, lineWidth: 1)
                        )
                }
                .accessibilityLabel("Open scenario picker")
            }

            HStack(spacing: 8) {
                StatusPill(
                    title: "Model",
                    value: scenario.modelState.title,
                    tint: scenario.modelState.tint
                )
                StatusPill(
                    title: "Safety",
                    value: scenario.safetyLevel.title,
                    tint: scenario.safetyLevel.tint
                )
                Spacer(minLength: 0)
            }
        }
        .padding(14)
        .glassCard(cornerRadius: 24, fill: Color.black.opacity(0.24))
    }
}

private struct StatusPill: View {
    let title: String
    let value: String
    let tint: Color

    var body: some View {
        HStack(spacing: 8) {
            Circle()
                .fill(tint)
                .frame(width: 8, height: 8)
            Text("\(title) \(value)")
                .font(.caption.weight(.bold))
                .foregroundStyle(.white)
                .lineLimit(1)
                .fixedSize(horizontal: true, vertical: false)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 8)
        .background(AppTheme.panelFillStrong, in: Capsule())
        .overlay(
            Capsule()
                .stroke(AppTheme.border, lineWidth: 1)
        )
    }
}

#Preview {
    ZStack {
        AppTheme.cameraGradient.ignoresSafeArea()
        TopStatusBar(scenario: PreviewScenarios.initial, onScenarioTap: {})
            .padding()
    }
}
