import SwiftUI

struct TopStatusBar: View {
    let scenario: OnSiteScenario
    let onScenarioTap: () -> Void

    var body: some View {
        HStack(alignment: .center, spacing: 10) {
            // Job + equipment
            VStack(alignment: .leading, spacing: 2) {
                Text(scenario.jobLabel.uppercased())
                    .font(.system(size: 9, weight: .bold))
                    .tracking(0.5)
                    .foregroundStyle(AppTheme.mist.opacity(0.45))
                Text(scenario.equipmentLabel)
                    .font(.subheadline.weight(.bold))
                    .foregroundStyle(.white)
                    .lineLimit(1)
                    .minimumScaleFactor(0.8)
            }

            Spacer(minLength: 0)

            // Status pills
            StatusDot(tint: scenario.modelState.tint, label: scenario.modelState.title, isActive: scenario.modelState == .listening || scenario.modelState == .reasoning)
            StatusDot(tint: scenario.safetyLevel.tint, label: scenario.safetyLevel.title, isActive: scenario.safetyLevel == .stop)
            OnDeviceChip()

            // Scenario picker
            Button(action: onScenarioTap) {
                Image(systemName: "slider.horizontal.3")
                    .font(.system(size: 12, weight: .bold))
                    .foregroundStyle(.white.opacity(0.6))
                    .frame(width: 32, height: 32)
                    .background(Color.white.opacity(0.06), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            }
            .accessibilityLabel("Scenario picker")
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
    }
}

// MARK: - Compact status dot

private struct StatusDot: View {
    let tint: Color
    let label: String
    let isActive: Bool

    @State private var pulse = false

    var body: some View {
        HStack(spacing: 4) {
            ZStack {
                if isActive {
                    Circle()
                        .fill(tint.opacity(0.3))
                        .frame(width: 12, height: 12)
                        .scaleEffect(pulse ? 1.5 : 1.0)
                        .opacity(pulse ? 0.0 : 0.5)
                }
                Circle()
                    .fill(tint)
                    .frame(width: 6, height: 6)
            }
            .frame(width: 12, height: 12)

            Text(label.uppercased())
                .font(.system(size: 9, weight: .heavy))
                .foregroundStyle(.white.opacity(0.7))
                .fixedSize()
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 5)
        .background(Color.white.opacity(0.05), in: Capsule())
        .onAppear {
            guard isActive else { return }
            withAnimation(.easeInOut(duration: 1.2).repeatForever(autoreverses: false)) {
                pulse = true
            }
        }
    }
}

// MARK: - On-device chip

private struct OnDeviceChip: View {
    var body: some View {
        HStack(spacing: 3) {
            Image(systemName: "iphone")
                .font(.system(size: 8, weight: .bold))
            Text("ON-DEVICE")
                .font(.system(size: 8, weight: .heavy))
                .tracking(0.6)
        }
        .foregroundStyle(AppTheme.accent)
        .padding(.horizontal, 8)
        .padding(.vertical, 5)
        .background(AppTheme.accent.opacity(0.10), in: Capsule())
    }
}

#Preview {
    VStack {
        TopStatusBar(scenario: PreviewScenarios.initial, onScenarioTap: {})
        Spacer()
    }
    .background(AppTheme.night.ignoresSafeArea())
}
