import SwiftUI

struct FindingBadge: View {
    let finding: MockFinding

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            RoundedRectangle(cornerRadius: 2)
                .fill(finding.severity.tint)
                .frame(width: 3)
                .frame(minHeight: 28)

            VStack(alignment: .leading, spacing: 3) {
                HStack {
                    Image(systemName: "scope")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(finding.severity.tint)
                    Text("Finding logged")
                        .font(.system(size: 10, weight: .heavy))
                        .tracking(0.4)
                        .foregroundStyle(finding.severity.tint)
                    Spacer()
                    Text(finding.location)
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(AppTheme.mist.opacity(0.4))
                }
                Text(finding.title)
                    .font(.subheadline.weight(.bold))
                    .foregroundStyle(.white.opacity(0.9))
                Text(finding.note)
                    .font(.caption.weight(.medium))
                    .foregroundStyle(AppTheme.mist.opacity(0.65))
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(12)
        .background(finding.severity.tint.opacity(0.06), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(finding.severity.tint.opacity(0.12), lineWidth: 0.75)
        )
    }
}

#Preview {
    ZStack {
        AppTheme.night.ignoresSafeArea()
        VStack(spacing: 10) {
            FindingBadge(finding: MockFinding(
                title: "Capacitor bulge",
                location: "Electrical compartment",
                severity: .caution,
                note: "Can top visibly domed above normal profile."
            ))
            FindingBadge(finding: MockFinding(
                title: "Exposed conductor",
                location: "Disconnect box",
                severity: .stop,
                note: "Insulation is split near the lug entry."
            ))
        }
        .padding()
    }
}
