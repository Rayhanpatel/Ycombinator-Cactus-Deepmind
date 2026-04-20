import SwiftUI

struct OnSiteView: View {
    private enum ActiveSheet: Identifiable {
        case closeJob
        case scenarios

        var id: Int {
            switch self {
            case .closeJob: 1
            case .scenarios: 2
            }
        }
    }

    @State private var selectedScenario = PreviewScenarios.initial
    @State private var activeSheet: ActiveSheet?

    var body: some View {
        VStack(spacing: 0) {
            // Zone 1: Status bar
            TopStatusBar(
                scenario: selectedScenario,
                onScenarioTap: { activeSheet = .scenarios }
            )

            // Zone 2: Compact camera strip
            CameraPlaceholderView(scenario: selectedScenario)
                .frame(height: 130)
                .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .stroke(AppTheme.borderSubtle, lineWidth: 0.75)
                )
                .padding(.horizontal, 14)
                .padding(.bottom, 4)

            // Zone 3: Chat timeline (fills remaining space)
            ChatTimeline(
                messages: selectedScenario.messages,
                stage: selectedScenario.stage
            )
            .frame(maxHeight: .infinity)

            // Zone 4: Voice input bar
            VoiceInputBar(
                stage: selectedScenario.stage,
                onCloseJobTap: { activeSheet = .closeJob }
            )
        }
        .background(AppTheme.night.ignoresSafeArea())
        .animation(.spring(response: 0.4, dampingFraction: 0.85), value: selectedScenario.id)
        .sheet(item: $activeSheet) { sheet in
            switch sheet {
            case .closeJob:
                CloseJobView(scenario: selectedScenario)
            case .scenarios:
                ScenarioPickerView(selectedScenario: $selectedScenario)
            }
        }
    }
}

#Preview {
    OnSiteView()
}
