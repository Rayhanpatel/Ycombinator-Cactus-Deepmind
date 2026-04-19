import SwiftUI

struct OnSiteView: View {
    private enum ActiveSheet: Identifiable {
        case closeJob
        case scenarios

        var id: Int {
            switch self {
            case .closeJob:
                1
            case .scenarios:
                2
            }
        }
    }

    @State private var selectedScenario = PreviewScenarios.initial
    @State private var activeSheet: ActiveSheet?

    var body: some View {
        ZStack {
            CameraPlaceholderView(scenario: selectedScenario)
                .ignoresSafeArea()

            VStack(spacing: 14) {
                TopStatusBar(
                    scenario: selectedScenario,
                    onScenarioTap: { activeSheet = .scenarios }
                )

                if let safetyMessage = selectedScenario.safetyMessage {
                    SafetyBanner(level: selectedScenario.safetyLevel, message: safetyMessage)
                }

                Spacer(minLength: 0)

                if let hypothesis = selectedScenario.hypothesis {
                    HypothesisCard(hypothesis: hypothesis)
                }

                VStack(spacing: 12) {
                    TranscriptCard(
                        lines: selectedScenario.transcriptLines,
                        stage: selectedScenario.stage,
                        footer: selectedScenario.transcriptFooter
                    )
                    FindingsDrawer(findings: selectedScenario.findings)
                    BottomActionBar(
                        stage: selectedScenario.stage,
                        onCloseJobTap: { activeSheet = .closeJob }
                    )
                }
            }
            .padding(.horizontal, 16)
            .padding(.top, 16)
            .padding(.bottom, 12)
        }
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
