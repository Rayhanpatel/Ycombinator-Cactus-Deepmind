import SwiftUI

struct ChatTimeline: View {
    let messages: [ChatMessage]
    let stage: SessionStage

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView(.vertical, showsIndicators: false) {
                LazyVStack(spacing: 10) {
                    ForEach(messages) { message in
                        messageView(for: message)
                            .id(message.id)
                            .transition(.opacity.combined(with: .move(edge: .bottom)))
                    }

                    // Spacer at bottom for breathing room
                    Color.clear.frame(height: 4)
                        .id("bottom")
                }
                .padding(.horizontal, 16)
                .padding(.top, 12)
                .padding(.bottom, 8)
            }
            .scrollDismissesKeyboard(.interactively)
            .onAppear {
                proxy.scrollTo("bottom", anchor: .bottom)
            }
        }
    }

    @ViewBuilder
    private func messageView(for message: ChatMessage) -> some View {
        switch message.kind {
        case .text(let speaker, let text):
            ChatBubbleView(speaker: speaker, text: text)

        case .hypothesis(let hypothesis):
            HypothesisCard(hypothesis: hypothesis)

        case .coaching(let data):
            CoachingCard(data: data)

        case .finding(let finding):
            FindingBadge(finding: finding)

        case .toolCall(let name, let detail):
            ToolCallBadge(name: name, detail: detail)

        case .safetyAlert(let level, let message):
            SafetyBanner(level: level, message: message)
        }
    }
}

#Preview {
    ZStack {
        AppTheme.night.ignoresSafeArea()
        ChatTimeline(
            messages: PreviewScenarios.carrierResponding.messages,
            stage: .assistantResponding
        )
    }
}
