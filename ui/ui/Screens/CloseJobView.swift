import SwiftUI

struct CloseJobView: View {
    @Environment(\.dismiss) private var dismiss

    let scenario: OnSiteScenario

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    summaryCard
                    findingsCard
                    notesCard
                }
                .padding(20)
            }
            .background(AppTheme.night.ignoresSafeArea())
            .navigationTitle("Close Job")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") {
                        dismiss()
                    }
                }
            }
        }
        .presentationDragIndicator(.visible)
    }

    private var summaryCard: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Resolution draft")
                .font(.system(.title2, design: .rounded, weight: .bold))
                .foregroundStyle(.white)

            SummaryRow(label: "Diagnosis", value: scenario.closeJobDraft.diagnosis)
            SummaryRow(label: "Fix applied", value: scenario.closeJobDraft.fixApplied)
            SummaryRow(label: "Time on site", value: "\(scenario.closeJobDraft.timeOnSiteMinutes) min")

            VStack(alignment: .leading, spacing: 8) {
                Text("Parts used")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(AppTheme.mist.opacity(0.72))
                FlowTagList(items: scenario.closeJobDraft.partsUsed.isEmpty ? ["No parts logged"] : scenario.closeJobDraft.partsUsed)
            }
        }
        .padding(20)
        .glassCard(cornerRadius: 28, fill: AppTheme.panelFillStrong)
    }

    private var findingsCard: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Logged findings")
                .font(.system(.title3, design: .rounded, weight: .bold))
                .foregroundStyle(.white)

            ForEach(scenario.findings) { finding in
                VStack(alignment: .leading, spacing: 6) {
                    HStack {
                        Text(finding.title)
                            .font(.headline.weight(.bold))
                            .foregroundStyle(.white)
                        Spacer()
                        Text(finding.location)
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(AppTheme.mist.opacity(0.7))
                    }
                    Text(finding.note)
                        .font(.subheadline.weight(.medium))
                        .foregroundStyle(AppTheme.mist)
                    Text("Severity: \(finding.severity.title)")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(finding.severity.tint)
                }
                .padding(.vertical, 6)
            }
        }
        .padding(20)
        .glassCard(cornerRadius: 28, fill: AppTheme.panelFill)
    }

    private var notesCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Technician note")
                .font(.system(.title3, design: .rounded, weight: .bold))
                .foregroundStyle(.white)
            Text(scenario.closeJobDraft.technicianNote)
                .font(.subheadline.weight(.medium))
                .foregroundStyle(AppTheme.mist)
            Button(action: {}) {
                Label("Export JSON (mock)", systemImage: "square.and.arrow.up")
                    .font(.headline.weight(.bold))
                    .foregroundStyle(.white)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 16)
                    .background(AppTheme.accent, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            }
            .buttonStyle(.plain)
        }
        .padding(20)
        .glassCard(cornerRadius: 28, fill: AppTheme.panelFill)
    }
}

private struct SummaryRow: View {
    let label: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.caption.weight(.bold))
                .foregroundStyle(AppTheme.mist.opacity(0.7))
            Text(value)
                .font(.body.weight(.semibold))
                .foregroundStyle(.white)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

private struct FlowTagList: View {
    let items: [String]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(items, id: \.self) { item in
                Text(item)
                    .font(.caption.weight(.bold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .background(AppTheme.graphite.opacity(0.8), in: Capsule())
            }
        }
    }
}

#Preview {
    CloseJobView(scenario: PreviewScenarios.closeJobScenario)
}
