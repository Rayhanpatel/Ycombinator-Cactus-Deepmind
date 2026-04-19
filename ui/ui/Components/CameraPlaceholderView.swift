import SwiftUI

struct CameraPlaceholderView: View {
    let scenario: OnSiteScenario

    var body: some View {
        ZStack {
            AppTheme.cameraGradient

            VStack(spacing: 28) {
                Spacer(minLength: 40)
                RoundedRectangle(cornerRadius: 36, style: .continuous)
                    .stroke(Color.white.opacity(0.18), style: StrokeStyle(lineWidth: 1.25, dash: [10, 10]))
                    .background(
                        RoundedRectangle(cornerRadius: 36, style: .continuous)
                            .fill(Color.white.opacity(0.04))
                    )
                    .frame(maxWidth: .infinity, minHeight: 330, maxHeight: 420)
                    .overlay {
                        ScanReticle()
                    }
                    .padding(.horizontal, 16)

                Spacer(minLength: 0)
            }

            AppTheme.overlayGradient
        }
    }
}

private struct ScanReticle: View {
    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 28, style: .continuous)
                .stroke(AppTheme.accent.opacity(0.38), lineWidth: 2)
                .frame(width: 220, height: 248)
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(Color.white.opacity(0.18), lineWidth: 1)
                .frame(width: 270, height: 300)
        }
    }
}

#Preview {
    CameraPlaceholderView(scenario: PreviewScenarios.initial)
}
