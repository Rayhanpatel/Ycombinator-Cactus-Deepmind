import SwiftUI

struct CoachingCard: View {
    let data: CoachingData

    @State private var completed: Set<Int> = []

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Header
            HStack(spacing: 8) {
                Image(systemName: "list.number")
                    .font(.system(size: 13, weight: .bold))
                    .foregroundStyle(AppTheme.accent)
                Text(data.title)
                    .font(.subheadline.weight(.bold))
                    .foregroundStyle(.white)
                Spacer()
                Text("\(completed.count)/\(data.steps.count)")
                    .font(.caption2.weight(.heavy))
                    .foregroundStyle(AppTheme.accent)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 3)
                    .background(AppTheme.accent.opacity(0.12), in: Capsule())
            }

            // Steps
            VStack(alignment: .leading, spacing: 6) {
                ForEach(Array(data.steps.enumerated()), id: \.offset) { index, step in
                    Button {
                        withAnimation(.spring(response: 0.3, dampingFraction: 0.7)) {
                            if completed.contains(index) {
                                completed.remove(index)
                            } else {
                                completed.insert(index)
                            }
                        }
                    } label: {
                        HStack(alignment: .top, spacing: 10) {
                            ZStack {
                                Circle()
                                    .stroke(completed.contains(index) ? AppTheme.success : AppTheme.steel.opacity(0.5), lineWidth: 1.5)
                                    .frame(width: 20, height: 20)
                                if completed.contains(index) {
                                    Circle()
                                        .fill(AppTheme.success)
                                        .frame(width: 20, height: 20)
                                        .overlay(
                                            Image(systemName: "checkmark")
                                                .font(.system(size: 10, weight: .bold))
                                                .foregroundStyle(.white)
                                        )
                                } else {
                                    Text("\(index + 1)")
                                        .font(.system(size: 10, weight: .heavy, design: .rounded))
                                        .foregroundStyle(AppTheme.mist.opacity(0.5))
                                }
                            }

                            Text(step)
                                .font(.caption.weight(.medium))
                                .foregroundStyle(completed.contains(index) ? AppTheme.mist.opacity(0.45) : AppTheme.mist.opacity(0.88))
                                .strikethrough(completed.contains(index), color: AppTheme.mist.opacity(0.3))
                                .fixedSize(horizontal: false, vertical: true)
                                .multilineTextAlignment(.leading)
                        }
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .padding(14)
        .glassCard(cornerRadius: 20, fill: AppTheme.accent.opacity(0.06), border: AppTheme.accent.opacity(0.18))
    }
}

#Preview {
    ZStack {
        AppTheme.night.ignoresSafeArea()
        CoachingCard(data: CoachingData(
            title: "Verify & replace capacitor",
            steps: [
                "Kill power at the disconnect",
                "Remove the service panel",
                "Discharge capacitor with insulated screwdriver",
                "Photo the wire positions",
                "Meter capacitance — expect 45 µF ± 6%",
                "Swap capacitor, match wire positions",
                "Restore panel and power",
                "Verify cooling at supply vent"
            ]
        ))
        .padding()
    }
}
