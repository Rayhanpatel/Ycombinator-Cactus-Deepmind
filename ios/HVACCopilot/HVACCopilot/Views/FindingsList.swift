// FindingsList.swift
// Log of what's been diagnosed this visit. Updates live as log_finding tool is called.

import SwiftUI

struct FindingsList: View {
    let findings: [Finding]

    var body: some View {
        List {
            if findings.isEmpty {
                ContentUnavailableView(
                    "No findings yet",
                    systemImage: "list.clipboard",
                    description: Text("Findings appear here as the copilot diagnoses issues.")
                )
            } else {
                ForEach(findings) { f in
                    FindingRow(finding: f)
                }
            }
        }
        .navigationTitle("Findings (\(findings.count))")
    }
}

private struct FindingRow: View {
    let finding: Finding

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                severityBadge
                Text(finding.location)
                    .font(.subheadline.weight(.semibold))
                Spacer()
                Text(finding.timestamp, style: .time)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Text(finding.issue)
                .font(.body)
            if let part = finding.partNumber {
                Label(part, systemImage: "wrench.and.screwdriver.fill")
                    .font(.caption.monospaced())
                    .foregroundStyle(.blue)
            }
            if let notes = finding.notes, !notes.isEmpty {
                Text(notes)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 4)
    }

    private var severityBadge: some View {
        let (color, label): (Color, String) = {
            switch finding.severity {
            case .info: return (.gray, "INFO")
            case .minor: return (.blue, "MINOR")
            case .major: return (.orange, "MAJOR")
            case .critical: return (.red, "CRIT")
            }
        }()
        return Text(label)
            .font(.caption2.weight(.bold))
            .padding(.horizontal, 6).padding(.vertical, 2)
            .foregroundStyle(.white)
            .background(color, in: Capsule())
    }
}

#Preview("With findings") {
    NavigationStack { FindingsList(findings: MockData.session.findings) }
}

#Preview("Empty") {
    NavigationStack { FindingsList(findings: []) }
}
