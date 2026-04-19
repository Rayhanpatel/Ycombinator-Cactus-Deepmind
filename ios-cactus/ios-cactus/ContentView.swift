//
//  ContentView.swift
//  ios-cactus
//
//  Created by t on 2026-04-18.
//

import SwiftUI
import PhotosUI
import UIKit

struct ContentView: View {
    @StateObject private var viewModel = ChatViewModel()
    @State private var selectedPhotoItem: PhotosPickerItem?

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
            .onChange(of: selectedPhotoItem) { _, newItem in
                guard let newItem else {
                    return
                }

                Task {
                    await viewModel.loadDraftPhoto(from: newItem)
                    selectedPhotoItem = nil
                }
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
                    Text("Send text, or attach a photo with an optional prompt after the model loads. The app replays the full chat history on each turn and keeps `auto_handoff` disabled.")
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
            if let photoAttachment = bubble.photoAttachment {
                attachmentPreview(for: photoAttachment, maxHeight: 220)
            }
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
        VStack(alignment: .leading, spacing: 12) {
            if let draftPhotoAttachment = viewModel.draftPhotoAttachment {
                HStack(alignment: .top, spacing: 12) {
                    attachmentPreview(for: draftPhotoAttachment, maxHeight: 120)
                        .frame(width: 120)

                    VStack(alignment: .leading, spacing: 8) {
                        Text("Attached photo")
                            .font(.subheadline.weight(.semibold))
                        Text("Gemma will receive this image path with your next user message.")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                        Button("Remove") {
                            viewModel.removeDraftPhoto()
                        }
                        .buttonStyle(.bordered)
                        .disabled(viewModel.isBusy)
                    }
                }
            }

            HStack(alignment: .bottom, spacing: 12) {
                PhotosPicker(selection: $selectedPhotoItem, matching: .images, photoLibrary: .shared()) {
                    Label("Photo", systemImage: "photo")
                }
                .buttonStyle(.bordered)
                .disabled(!viewModel.canCompose || viewModel.isGenerating)

                TextField("Ask Gemma about text or a photo…", text: $viewModel.input, axis: .vertical)
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

    @ViewBuilder
    private func attachmentPreview(for photoAttachment: PhotoAttachment, maxHeight: CGFloat) -> some View {
        if let image = UIImage(contentsOfFile: photoAttachment.fileURL.path) {
            Image(uiImage: image)
                .resizable()
                .scaledToFit()
                .frame(maxHeight: maxHeight)
                .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        } else {
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(Color(uiColor: .secondarySystemBackground))
                .frame(height: maxHeight)
                .overlay {
                    Label("Image unavailable", systemImage: "exclamationmark.triangle")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
        }
    }
}

struct ContentView_Previews: PreviewProvider {
    static var previews: some View {
        ContentView()
    }
}
