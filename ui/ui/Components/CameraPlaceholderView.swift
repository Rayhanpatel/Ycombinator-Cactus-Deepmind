import SwiftUI

struct CameraPlaceholderView: View {
    let scenario: OnSiteScenario

    var body: some View {
        ZStack {
            AppTheme.cameraGradient

            VStack(spacing: 28) {
                HStack {
                    VStack(alignment: .leading, spacing: 8) {
                        Label("Camera preview", systemImage: "camera.viewfinder")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(AppTheme.mist.opacity(0.78))
                        Text(scenario.sceneLabel)
                            .font(.system(.headline, design: .rounded, weight: .semibold))
                            .foregroundStyle(.white)
                    }
                    Spacer()
                }
                .padding(.horizontal, 20)

                RoundedRectangle(cornerRadius: 36, style: .continuous)
                    .stroke(Color.white.opacity(0.18), style: StrokeStyle(lineWidth: 1.25, dash: [10, 10]))
                    .background(
                        RoundedRectangle(cornerRadius: 36, style: .continuous)
                            .fill(Color.white.opacity(0.04))
                    )
                    .frame(maxWidth: .infinity, minHeight: 330, maxHeight: 420)
                    .overlay(alignment: .topLeading) {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Tracked unit")
                                .font(.caption.weight(.bold))
                                .foregroundStyle(.white.opacity(0.84))
                            Text(scenario.equipmentLabel)
                                .font(.system(.title3, design: .rounded, weight: .bold))
                                .foregroundStyle(.white)
                        }
                        .padding(18)
                    }
                    .overlay(alignment: .bottomLeading) {
                        HStack(spacing: 10) {
                            Image(systemName: "fanblades.fill")
                                .foregroundStyle(AppTheme.accent)
                            Text("Camera-first mock. Live media wiring comes later.")
                                .font(.caption.weight(.medium))
                                .foregroundStyle(AppTheme.mist)
                        }
                        .padding(16)
                    }
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
                .stroke(AppTheme.accent.opacity(0.55), lineWidth: 2)
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
