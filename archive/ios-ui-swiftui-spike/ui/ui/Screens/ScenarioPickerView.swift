import SwiftUI

struct ScenarioPickerView: View {
    @Environment(\.dismiss) private var dismiss

    @Binding var selectedScenario: OnSiteScenario

    var body: some View {
        NavigationStack {
            List {
                Section("Mock states") {
                    ForEach(PreviewScenarios.all) { scenario in
                        Button {
                            selectedScenario = scenario
                            dismiss()
                        } label: {
                            HStack(spacing: 14) {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(scenario.name)
                                        .font(.headline.weight(.bold))
                                        .foregroundStyle(.white)
                                    Text("\(scenario.equipmentLabel) • \(scenario.stage.rawValue)")
                                        .font(.caption.weight(.semibold))
                                        .foregroundStyle(AppTheme.mist.opacity(0.7))
                                }
                                Spacer()
                                if scenario.id == selectedScenario.id {
                                    Image(systemName: "checkmark.circle.fill")
                                        .foregroundStyle(AppTheme.accent)
                                }
                            }
                            .padding(.vertical, 6)
                        }
                        .listRowBackground(AppTheme.graphite.opacity(0.76))
                    }
                }
            }
            .scrollContentBackground(.hidden)
            .background(AppTheme.night.ignoresSafeArea())
            .navigationTitle("Scenario picker")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") {
                        dismiss()
                    }
                }
            }
        }
        .presentationDragIndicator(.visible)
    }
}

#Preview {
    ScenarioPickerView(selectedScenario: .constant(PreviewScenarios.initial))
}
