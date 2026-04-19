import SwiftUI

struct TopStatusBar: View {
    let scenario: OnSiteScenario
    let onScenarioTap: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 6) {
                Text(scenario.jobLabel.uppercased())
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(AppTheme.mist.opacity(0.72))
                Text(scenario.equipmentLabel)
                    .font(.system(.title3, design: .rounded, weight: .bold))
                    .foregroundStyle(.white)
            }

            Spacer(minLength: 0)

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
        }
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
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(AppTheme.mist.opacity(0.66))
                Text(value)
                    .font(.caption.weight(.bold))
                    .foregroundStyle(.white)
            }
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
