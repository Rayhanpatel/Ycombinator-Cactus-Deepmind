import SwiftUI

struct BottomActionBar: View {
    let stage: SessionStage
    let onCloseJobTap: () -> Void

    var body: some View {
        HStack(spacing: 16) {
            TalkButton(stage: stage)
                .frame(maxWidth: .infinity)

            Button(action: onCloseJobTap) {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Close Job")
                        .font(.headline.weight(.bold))
                    Text("Review the structured resolution draft")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(AppTheme.mist.opacity(0.72))
                }
                .foregroundStyle(.white)
                .frame(maxWidth: .infinity, minHeight: 90, alignment: .leading)
                .padding(.horizontal, 18)
                .background(
                    LinearGradient(
                        colors: [AppTheme.panelFillStrong, AppTheme.graphite.opacity(0.95)],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    ),
                    in: RoundedRectangle(cornerRadius: 26, style: .continuous)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 26, style: .continuous)
                        .stroke(AppTheme.border, lineWidth: 1)
                )
            }
            .buttonStyle(.plain)
        }
    }
}

#Preview {
    ZStack {
        AppTheme.cameraGradient.ignoresSafeArea()
        BottomActionBar(stage: .assistantResponding, onCloseJobTap: {})
            .padding()
    }
}
