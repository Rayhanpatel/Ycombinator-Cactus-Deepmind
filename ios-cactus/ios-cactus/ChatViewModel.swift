import Foundation
import Combine
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

    init(id: UUID = UUID(), role: Role, text: String) {
        self.id = id
        self.role = role
        self.text = text
    }
}

@MainActor
final class ChatViewModel: ObservableObject {
    @Published var input = ""
    @Published private(set) var bubbles: [ChatBubble] = []
    @Published private(set) var status = "Looking for a local Gemma model…"
    @Published private(set) var modelDescription = "No model loaded yet."
    @Published private(set) var isGenerating = false
    @Published private(set) var isLoadingModel = false

    private let service = CactusGemmaService()
    private var hasBooted = false

    private let systemPrompt = "You are a concise assistant running entirely on-device on an iPhone through Cactus. Answer in plain text."

    var setupHint: String {
        AppModelLocation.setupHint
    }

    var canCompose: Bool {
        !isLoadingModel
    }

    var canSend: Bool {
        !isBusy && !input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && status.hasPrefix("Ready")
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

        bubbles.removeAll()
    }

    func send() async {
        let prompt = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !prompt.isEmpty, !isBusy else {
            return
        }

        input = ""
        isGenerating = true
        status = "Generating…"

        defer {
            isGenerating = false
        }

        let userBubble = ChatBubble(role: .user, text: prompt)
        let assistantBubbleID = UUID()

        let history = bubbles + [userBubble]
        bubbles = history + [ChatBubble(id: assistantBubbleID, role: .assistant, text: "")]

        let llmMessages = [LLMMessage(role: "system", content: systemPrompt)] + history.map { bubble in
            LLMMessage(role: bubble.role.rawValue, content: bubble.text)
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
