import SwiftUI

struct FindingsDrawer: View {
    let findings: [MockFinding]

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            RoundedRectangle(cornerRadius: 999, style: .continuous)
                .fill(Color.white.opacity(0.18))
                .frame(width: 42, height: 5)
                .frame(maxWidth: .infinity)

            HStack {
                Label("Findings", systemImage: "list.bullet.clipboard")
                    .font(.headline.weight(.bold))
                    .foregroundStyle(.white)
                Spacer()
                Text("\(findings.count)")
                    .font(.headline.weight(.heavy))
                    .foregroundStyle(AppTheme.accent)
            }

            if findings.isEmpty {
                Text("No findings logged yet. The drawer is here to validate density and placement on iPhone.")
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(AppTheme.mist.opacity(0.84))
            } else {
                VStack(spacing: 10) {
                    ForEach(findings.prefix(3)) { finding in
                        HStack(alignment: .top, spacing: 12) {
                            Circle()
                                .fill(finding.severity.tint)
                                .frame(width: 10, height: 10)
                                .padding(.top, 5)
                            VStack(alignment: .leading, spacing: 4) {
                                HStack {
                                    Text(finding.title)
                                        .font(.subheadline.weight(.bold))
                                        .foregroundStyle(.white)
                                    Spacer()
                                    Text(finding.location)
                                        .font(.caption.weight(.semibold))
                                        .foregroundStyle(AppTheme.mist.opacity(0.72))
                                }
                                Text(finding.note)
                                    .font(.caption.weight(.medium))
                                    .foregroundStyle(AppTheme.mist)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                    }
                }
            }
        }
        .padding(18)
        .glassCard(cornerRadius: 28, fill: Color.black.opacity(0.46))
    }
}

#Preview {
    ZStack {
        AppTheme.cameraGradient.ignoresSafeArea()
        FindingsDrawer(findings: PreviewScenarios.initial.findings)
            .padding()
    }
}
