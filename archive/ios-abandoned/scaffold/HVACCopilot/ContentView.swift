// ContentView.swift
// T+0 → T+2h SPIKE UI. One screen: load model, type prompt, see reply.
// This is the Path A gate. If this works on device by T+2h, we commit to on-device.
// After the spike passes, this view gets replaced by OnSiteView as the root.

import SwiftUI

struct ContentView: View {
    @State private var modelState: ModelState = .idle
    @State private var prompt: String = "In one sentence: what causes an AC condenser to short cycle?"
    @State private var reply: String = ""
    @State private var isRunning: Bool = false
    @State private var elapsedMs: Int = 0

    enum ModelState: Equatable {
        case idle
        case loading
        case loaded
        case failed(String)
    }

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 16) {
                header

                Group {
                    switch modelState {
                    case .idle:
                        Button("Load Gemma 4 E4B") { Task { await loadModel() } }
                            .buttonStyle(.borderedProminent)
                    case .loading:
                        HStack { ProgressView(); Text("Loading model…") }
                    case .loaded:
                        Label("Model loaded ✓", systemImage: "checkmark.seal.fill")
                            .foregroundStyle(.green)
                    case .failed(let err):
                        Label(err, systemImage: "xmark.octagon.fill")
                            .foregroundStyle(.red)
                            .font(.caption)
                    }
                }

                Divider()

                Text("Prompt").font(.headline)
                TextEditor(text: $prompt)
                    .frame(minHeight: 80)
                    .border(.secondary.opacity(0.3))
                    .disabled(modelState != .loaded)

                Button(action: { Task { await runCompletion() } }) {
                    HStack {
                        if isRunning { ProgressView().controlSize(.small) }
                        Text(isRunning ? "Running…" : "Send")
                    }
                }
                .buttonStyle(.borderedProminent)
                .disabled(modelState != .loaded || isRunning || prompt.isEmpty)

                if !reply.isEmpty {
                    Divider()
                    HStack {
                        Text("Reply").font(.headline)
                        Spacer()
                        if elapsedMs > 0 { Text("\(elapsedMs) ms").font(.caption).foregroundStyle(.secondary) }
                    }
                    ScrollView {
                        Text(reply)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(8)
                            .background(.secondary.opacity(0.1))
                            .cornerRadius(8)
                    }
                }

                Spacer()
            }
            .padding()
            .navigationTitle("HVAC Copilot — Spike")
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Path A spike").font(.caption).foregroundStyle(.secondary)
            Text("Goal: one coherent reply from the model on device by T+2h.")
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
    }

    // MARK: - Actions

    private func loadModel() async {
        modelState = .loading
        do {
            try await CactusModel.shared.load()
            modelState = .loaded
        } catch {
            modelState = .failed(error.localizedDescription)
        }
    }

    private func runCompletion() async {
        isRunning = true
        reply = ""
        elapsedMs = 0
        let start = Date()
        do {
            let text = try await CactusModel.shared.completeText(prompt)
            reply = text
        } catch {
            reply = "ERROR: \(error.localizedDescription)"
        }
        elapsedMs = Int(Date().timeIntervalSince(start) * 1000)
        isRunning = false
    }
}

#Preview {
    ContentView()
}
