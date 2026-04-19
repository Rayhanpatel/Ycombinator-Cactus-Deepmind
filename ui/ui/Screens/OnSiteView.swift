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
        GeometryReader { geometry in
            ZStack {
                CameraPlaceholderView(scenario: selectedScenario)
                    .ignoresSafeArea()
            }
            .overlay(alignment: .top) {
                VStack(spacing: 10) {
                    TopStatusBar(
                        scenario: selectedScenario,
                        onScenarioTap: { activeSheet = .scenarios }
                    )

                    if let safetyMessage = selectedScenario.safetyMessage {
                        SafetyBanner(level: selectedScenario.safetyLevel, message: safetyMessage)
                    }
                }
                .padding(.horizontal, 16)
                .padding(.top, geometry.safeAreaInsets.top + 8)
            }
            .overlay(alignment: .top) {
                if let hypothesis = selectedScenario.hypothesis {
                    HypothesisCard(hypothesis: hypothesis)
                        .padding(.horizontal, 16)
                        .padding(.top, geometry.safeAreaInsets.top + topOverlayOffset)
                }
            }
            .overlay(alignment: .bottom) {
                VStack(spacing: 10) {
                    ScrollView(.vertical, showsIndicators: false) {
                        VStack(spacing: 10) {
                            TranscriptCard(
                                lines: selectedScenario.transcriptLines,
                                stage: selectedScenario.stage,
                                footer: selectedScenario.transcriptFooter
                            )

                            FindingsDrawer(findings: selectedScenario.findings)
                        }
                        .padding(.top, 8)
                    }
                    .frame(maxHeight: scrollContentHeight(for: geometry.size.height, bottomInset: geometry.safeAreaInsets.bottom))
                    .scrollBounceBehavior(.basedOnSize)

                    BottomActionBar(
                        stage: selectedScenario.stage,
                        onCloseJobTap: { activeSheet = .closeJob }
                    )
                }
                .padding(.horizontal, 16)
                .padding(.bottom, max(geometry.safeAreaInsets.bottom, 12))
            }
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

    private var topOverlayOffset: CGFloat {
        switch selectedScenario.stage {
        case .safetyAlert:
            146
        default:
            126
        }
    }

    private func scrollContentHeight(for screenHeight: CGFloat, bottomInset: CGFloat) -> CGFloat {
        let available = screenHeight - bottomInset
        return min(max(available * 0.24, 176), 236)
    }
}

#Preview {
    OnSiteView()
}
