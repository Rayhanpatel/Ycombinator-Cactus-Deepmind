//
//  ContentView.swift
//  ios-cactus
//
//  Created by t on 2026-04-18.
//

import SwiftUI

struct ContentView: View {
    @StateObject private var viewModel = ChatViewModel()

    var body: some View {
        NavigationStack {
            VStack(spacing: 16) {
                statusCard
                conversation
                composer
            }
            .padding(16)
            .navigationTitle("Cactus Gemma")
            .task {
                await viewModel.bootIfNeeded()
            }
        }
    }

    private var statusCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(viewModel.status)
                    .font(.headline)
                Spacer()
                Button("Reload") {
                    Task {
                        await viewModel.reloadModel()
                    }
                }
                .buttonStyle(.bordered)
                .disabled(viewModel.isBusy)
            }

            Text(viewModel.modelDescription)
                .font(.footnote)
                .foregroundStyle(.secondary)
                .textSelection(.enabled)

            Text(viewModel.setupHint)
                .font(.footnote)
                .foregroundStyle(.secondary)

            HStack {
                Button("Clear Chat") {
                    viewModel.clearConversation()
                }
                .buttonStyle(.bordered)
                .disabled(viewModel.isGenerating || viewModel.bubbles.isEmpty)

                Spacer()

                if viewModel.isGenerating {
                    ProgressView()
                        .controlSize(.small)
                }
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
    }

    private var conversation: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 12) {
                if viewModel.bubbles.isEmpty {
                    Text("Send a short prompt after the model loads. The app replays the full text chat history on each turn and keeps `auto_handoff` disabled.")
                        .font(.body)
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(16)
                        .background(Color(uiColor: .secondarySystemBackground), in: RoundedRectangle(cornerRadius: 18, style: .continuous))
                }

                ForEach(viewModel.bubbles) { bubble in
                    HStack {
                        if bubble.role == .assistant {
                            bubbleView(bubble)
                            Spacer(minLength: 32)
                        } else {
                            Spacer(minLength: 32)
                            bubbleView(bubble)
                        }
                    }
                }
            }
        }
        .scrollDismissesKeyboard(.interactively)
    }

    private func bubbleView(_ bubble: ChatBubble) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(bubble.role.title)
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            Text(bubble.text.isEmpty ? "…" : bubble.text)
                .font(.body)
                .textSelection(.enabled)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(bubble.role.backgroundStyle, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
    }

    private var composer: some View {
        HStack(alignment: .bottom, spacing: 12) {
            TextField("Ask Gemma something simple…", text: $viewModel.input, axis: .vertical)
                .textFieldStyle(.roundedBorder)
                .lineLimit(1...5)
                .disabled(!viewModel.canCompose)

            Button(viewModel.isGenerating ? "Running…" : "Send") {
                Task {
                    await viewModel.send()
                }
            }
            .buttonStyle(.borderedProminent)
            .disabled(!viewModel.canSend)
        }
    }
}

struct ContentView_Previews: PreviewProvider {
    static var previews: some View {
        ContentView()
    }
}
