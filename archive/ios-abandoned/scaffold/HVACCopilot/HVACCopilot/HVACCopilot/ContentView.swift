//
//  ContentView.swift
//  HVACCopilot — T+2h spike UI.
//
//  Purpose: confirm Gemma 4 E4B loads via Cactus on the iPhone 16 Pro
//  and returns a coherent text reply. One button to load, one prompt
//  field to send, one result area. This screen gets replaced by OnSiteView
//  once the gate is green.

import SwiftUI

struct ContentView: View {
    @State private var loadState: LoadState = .idle
    @State private var prompt: String = "what is 2+2?"
    @State private var response: String = ""
    @State private var isSending: Bool = false
    @State private var errorMessage: String?
    @State private var loadDurationSeconds: Double?

    var body: some View {
        NavigationStack {
            Form {
                modelSection
                promptSection
                if !response.isEmpty { responseSection }
                if let err = errorMessage { errorSection(err) }
            }
            .navigationTitle("HVAC Copilot — Spike")
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    // MARK: - Sections

    private var modelSection: some View {
        Section("Model") {
            HStack {
                statusLabel
                Spacer()
                if loadState == .loading { ProgressView() }
            }
            if let d = loadDurationSeconds {
                Text(String(format: "Loaded in %.1fs", d))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Button(action: loadModel) {
                Text(loadState == .loaded ? "Reload Model" : "Load Gemma 4 E4B")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .disabled(loadState == .loading)
        }
    }

    private var promptSection: some View {
        Section("Prompt") {
            TextField("Ask something", text: $prompt, axis: .vertical)
                .lineLimit(2...5)
                .textInputAutocapitalization(.never)
            Button(action: sendPrompt) {
                HStack {
                    Text("Send")
                    Spacer()
                    if isSending { ProgressView() }
                }
            }
            .disabled(isSending || prompt.trimmingCharacters(in: .whitespaces).isEmpty || loadState != .loaded)
        }
    }

    private var responseSection: some View {
        Section("Response") {
            Text(response)
                .font(.system(.body, design: .monospaced))
                .textSelection(.enabled)
        }
    }

    private func errorSection(_ err: String) -> some View {
        Section("Error") {
            Text(err)
                .font(.caption)
                .foregroundStyle(.red)
                .textSelection(.enabled)
        }
    }

    private var statusLabel: some View {
        switch loadState {
        case .idle:
            return Text("Not loaded").foregroundStyle(.secondary)
        case .loading:
            return Text("Loading…").foregroundStyle(.secondary)
        case .loaded:
            return Text("Loaded ✓").foregroundStyle(.green)
        case .failed:
            return Text("Load failed").foregroundStyle(.red)
        }
    }

    // MARK: - Actions

    private func loadModel() {
        errorMessage = nil
        loadState = .loading
        loadDurationSeconds = nil
        let started = Date()
        Task {
            do {
                try await CactusModel.shared.load()
                loadDurationSeconds = Date().timeIntervalSince(started)
                loadState = .loaded
            } catch {
                errorMessage = error.localizedDescription
                loadState = .failed
            }
        }
    }

    private func sendPrompt() {
        errorMessage = nil
        isSending = true
        response = ""
        let userText = prompt
        Task {
            do {
                let reply = try await CactusModel.shared.completeText(userText)
                response = reply
            } catch {
                errorMessage = error.localizedDescription
            }
            isSending = false
        }
    }
}

// MARK: - State

private enum LoadState {
    case idle, loading, loaded, failed
}

#Preview {
    ContentView()
}
