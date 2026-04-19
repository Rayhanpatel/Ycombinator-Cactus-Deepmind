// CloseJobView.swift
// End-of-visit summary screen. Fed by the close_job tool call.

import SwiftUI

struct CloseJobView: View {
    let session: SessionState
    @State private var summary: String = "Replaced failed run capacitor on outdoor condenser. Unit cycling normally. Tested 3 cooling cycles — no short cycling observed. Customer informed."
    @State private var partsUsed: [String] = ["P291-4554RS"]
    @State private var followUp: Bool = false

    var body: some View {
        Form {
            Section("Summary") {
                TextEditor(text: $summary).frame(minHeight: 120)
            }

            Section("Parts used") {
                if partsUsed.isEmpty {
                    Text("None").foregroundStyle(.secondary)
                } else {
                    ForEach(partsUsed, id: \.self) { p in
                        Label(p, systemImage: "wrench.and.screwdriver.fill")
                            .font(.body.monospaced())
                    }
                }
            }

            Section("Findings (\(session.findings.count))") {
                ForEach(session.findings) { f in
                    VStack(alignment: .leading) {
                        Text(f.issue).font(.subheadline.weight(.medium))
                        Text(f.location).font(.caption).foregroundStyle(.secondary)
                    }
                }
            }

            Section("Follow-up") {
                Toggle("Follow-up visit required", isOn: $followUp)
            }

            Section {
                Button {
                    // Hook up to close_job tool at T+4h
                } label: {
                    HStack {
                        Spacer()
                        Label("Finalize & send", systemImage: "paperplane.fill")
                            .fontWeight(.semibold)
                        Spacer()
                    }
                }
                .buttonStyle(.borderedProminent)
            }
        }
        .navigationTitle("Close job")
        .navigationBarTitleDisplayMode(.inline)
    }
}

#Preview {
    NavigationStack { CloseJobView(session: MockData.session) }
}
