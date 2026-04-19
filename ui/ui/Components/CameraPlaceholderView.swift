import SwiftUI

struct CameraPlaceholderView: View {
    let scenario: OnSiteScenario

    @State private var scanOffset: CGFloat = -1.0

    var body: some View {
        ZStack {
            // Base gradient
            AppTheme.cameraGradient

            // State-based vignette
            RadialGradient(
                colors: [
                    AppTheme.vignetteColor(for: scenario.stage),
                    Color.clear
                ],
                center: .center,
                startRadius: 20,
                endRadius: 200
            )
            .animation(.easeInOut(duration: 0.8), value: scenario.stage)

            // Scan line
            if scenario.stage == .listening || scenario.stage == .assistantResponding {
                GeometryReader { geo in
                    let y = (geo.size.height / 2) + (scanOffset * geo.size.height * 0.3)
                    Rectangle()
                        .fill(
                            LinearGradient(
                                colors: [.clear, scanTint.opacity(0.4), scanTint.opacity(0.6), scanTint.opacity(0.4), .clear],
                                startPoint: .leading,
                                endPoint: .trailing
                            )
                        )
                        .frame(height: 1.5)
                        .position(x: geo.size.width / 2, y: y)
                }
            }

            // Corner brackets
            GeometryReader { geo in
                let inset: CGFloat = 12
                let len: CGFloat = 20
                let lw: CGFloat = 2.0

                Path { path in
                    // Top-left
                    path.move(to: CGPoint(x: inset + len, y: inset))
                    path.addLine(to: CGPoint(x: inset, y: inset))
                    path.addLine(to: CGPoint(x: inset, y: inset + len))
                    // Top-right
                    path.move(to: CGPoint(x: geo.size.width - inset - len, y: inset))
                    path.addLine(to: CGPoint(x: geo.size.width - inset, y: inset))
                    path.addLine(to: CGPoint(x: geo.size.width - inset, y: inset + len))
                    // Bottom-left
                    path.move(to: CGPoint(x: inset, y: geo.size.height - inset - len))
                    path.addLine(to: CGPoint(x: inset, y: geo.size.height - inset))
                    path.addLine(to: CGPoint(x: inset + len, y: geo.size.height - inset))
                    // Bottom-right
                    path.move(to: CGPoint(x: geo.size.width - inset, y: geo.size.height - inset - len))
                    path.addLine(to: CGPoint(x: geo.size.width - inset, y: geo.size.height - inset))
                    path.addLine(to: CGPoint(x: geo.size.width - inset - len, y: geo.size.height - inset))
                }
                .stroke(AppTheme.accent.opacity(0.6), style: StrokeStyle(lineWidth: lw, lineCap: .round))
            }
        }
        .onAppear {
            withAnimation(.easeInOut(duration: 2.4).repeatForever(autoreverses: true)) {
                scanOffset = 1.0
            }
        }
    }

    private var scanTint: Color {
        scenario.stage == .listening ? AppTheme.listening : AppTheme.accent
    }
}

#Preview {
    CameraPlaceholderView(scenario: PreviewScenarios.initial)
        .frame(height: 130)
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .padding()
        .background(AppTheme.night)
}
