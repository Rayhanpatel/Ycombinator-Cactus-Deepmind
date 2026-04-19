import Foundation
import Combine
import PhotosUI
import SwiftUI

struct ChatBubble: Identifiable, Sendable {
    enum Role: String, Sendable {
        case user
        case assistant

        var title: String {
            switch self {
            case .user:
                return "You"
            case .assistant:
                return "Gemma"
            }
        }

        var backgroundStyle: Color {
            switch self {
            case .user:
                return Color.accentColor.opacity(0.18)
            case .assistant:
                return Color(uiColor: .secondarySystemBackground)
            }
        }
    }

    let id: UUID
    let role: Role
    var text: String
    let photoAttachment: PhotoAttachment?

    init(id: UUID = UUID(), role: Role, text: String, photoAttachment: PhotoAttachment? = nil) {
        self.id = id
        self.role = role
        self.text = text
        self.photoAttachment = photoAttachment
    }
}

@MainActor
final class ChatViewModel: ObservableObject {
    @Published var input = ""
    @Published private(set) var bubbles: [ChatBubble] = []
    @Published private(set) var draftPhotoAttachment: PhotoAttachment?
    @Published private(set) var status = "Looking for a local Gemma model…"
    @Published private(set) var modelDescription = "No model loaded yet."
    @Published private(set) var isGenerating = false
    @Published private(set) var isLoadingModel = false

    private let service = CactusGemmaService()
    private let photoAttachmentStore = PhotoAttachmentStore()
    private var hasBooted = false

    private let systemPrompt = "You are a concise assistant running entirely on-device on an iPhone through Cactus. Answer in plain text."
    private let defaultPhotoPrompt = "Describe this photo."

    var setupHint: String {
        AppModelLocation.setupHint
    }

    var canCompose: Bool {
        !isLoadingModel
    }

    var canSend: Bool {
        !isBusy && (!input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || draftPhotoAttachment != nil) && status.hasPrefix("Ready")
    }

    var isBusy: Bool {
        isGenerating || isLoadingModel
    }

    func bootIfNeeded() async {
        guard !hasBooted else {
            return
        }

        hasBooted = true
        await reloadModel()
    }

    func reloadModel() async {
        guard !isGenerating else {
            return
        }

        isLoadingModel = true
        status = "Loading model…"

        defer {
            isLoadingModel = false
        }

        do {
            let selection = try AppModelLocation.resolve()
            modelDescription = selection.description
            try await service.loadModel(at: selection.url)
            status = "Ready"
        } catch {
            modelDescription = "No valid model directory is available yet."
            status = "Load failed"
            if bubbles.isEmpty {
                bubbles = [
                    ChatBubble(role: .assistant, text: error.localizedDescription),
                ]
            }
        }
    }

    func clearConversation() {
        guard !isGenerating else {
            return
        }

        if let draftPhotoAttachment {
            photoAttachmentStore.discard(draftPhotoAttachment)
            self.draftPhotoAttachment = nil
        }

        bubbles.removeAll()
        photoAttachmentStore.resetSession()
    }

    func loadDraftPhoto(from item: PhotosPickerItem) async {
        guard !isBusy else {
            return
        }

        do {
            guard let photoData = try await item.loadTransferable(type: Data.self) else {
                throw NSError(
                    domain: "ChatViewModel",
                    code: 20,
                    userInfo: [NSLocalizedDescriptionKey: "The selected photo could not be read from the photo library."]
                )
            }

            if let draftPhotoAttachment {
                photoAttachmentStore.discard(draftPhotoAttachment)
            }

            draftPhotoAttachment = try photoAttachmentStore.persistPhoto(data: photoData)
            if status.hasPrefix("Ready") {
                status = "Ready • Photo attached"
            }
        } catch {
            status = status.hasPrefix("Ready") ? "Ready • Photo attach failed" : "Photo attach failed"
        }
    }

    func removeDraftPhoto() {
        guard let draftPhotoAttachment else {
            return
        }

        photoAttachmentStore.discard(draftPhotoAttachment)
        self.draftPhotoAttachment = nil
        if status.hasPrefix("Ready") {
            status = "Ready"
        }
    }

    func send() async {
        let rawPrompt = input.trimmingCharacters(in: .whitespacesAndNewlines)
        let photoAttachment = draftPhotoAttachment

        guard !isBusy else {
            return
        }

        guard !rawPrompt.isEmpty || photoAttachment != nil else {
            return
        }

        let prompt = rawPrompt.isEmpty ? defaultPhotoPrompt : rawPrompt
        input = ""
        draftPhotoAttachment = nil
        isGenerating = true
        status = "Generating…"

        defer {
            isGenerating = false
        }

        let userBubble = ChatBubble(role: .user, text: prompt, photoAttachment: photoAttachment)
        let assistantBubbleID = UUID()

        let history = bubbles + [userBubble]
        bubbles = history + [ChatBubble(id: assistantBubbleID, role: .assistant, text: "")]

        let llmMessages = [LLMMessage(role: "system", content: systemPrompt)] + history.map { bubble in
            LLMMessage(
                role: bubble.role.rawValue,
                content: bubble.text,
                images: bubble.photoAttachment.map { [$0.fileURL.path] }
            )
        }

        do {
            let response = try await service.generate(messages: llmMessages) { [weak self] token in
                Task { @MainActor [weak self, assistantBubbleID] in
                    self?.appendToken(token, to: assistantBubbleID)
                }
            }

            if let finalResponse = response.response, !finalResponse.isEmpty {
                updateBubble(id: assistantBubbleID, text: finalResponse)
            } else if bubbleText(for: assistantBubbleID).isEmpty {
                updateBubble(id: assistantBubbleID, text: "No text was returned.")
            }

            status = statusText(for: response)
        } catch {
            updateBubble(id: assistantBubbleID, text: "Error: \(error.localizedDescription)")
            status = "Generation failed"
        }
    }

    private func appendToken(_ token: String, to bubbleID: UUID) {
        guard let index = bubbles.firstIndex(where: { $0.id == bubbleID }) else {
            return
        }

        bubbles[index].text += token
    }

    private func updateBubble(id: UUID, text: String) {
        guard let index = bubbles.firstIndex(where: { $0.id == id }) else {
            return
        }

        bubbles[index].text = text
    }

    private func bubbleText(for bubbleID: UUID) -> String {
        bubbles.first(where: { $0.id == bubbleID })?.text ?? ""
    }

    private func statusText(for response: LLMResponse) -> String {
        var parts = ["Ready"]

        if let ttft = response.timeToFirstTokenMs {
            parts.append(String(format: "TTFT %.0f ms", ttft))
        }
        if let decodeTps = response.decodeTps {
            parts.append(String(format: "%.1f tok/s", decodeTps))
        }
        if let ramUsageMb = response.ramUsageMb {
            parts.append(String(format: "%.0f MB", ramUsageMb))
        }

        return parts.joined(separator: " • ")
    }
}
