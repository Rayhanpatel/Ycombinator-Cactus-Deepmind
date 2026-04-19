// HUDOverlay.swift
// Top-of-screen heads-up: current hypothesis, safety state, last assistant message.

import SwiftUI

struct HUDOverlay: View {
    let session: SessionState

    var body: some View {
        VStack(spacing: 10) {
            safetyBanner
            hypothesisCard
            lastAssistantBubble
        }
    }

    @ViewBuilder
    private var safetyBanner: some View {
        switch session.safetyLevel {
        case .normal:
            EmptyView()
        case .caution:
            banner(text: "CAUTION — proceed with care", color: .orange, icon: "exclamationmark.triangle.fill")
        case .stop:
            banner(text: "STOP — hazard detected", color: .red, icon: "hand.raised.fill")
        }
    }

    private func banner(text: String, color: Color, icon: String) -> some View {
        HStack {
            Image(systemName: icon)
            Text(text).fontWeight(.semibold)
            Spacer()
        }
        .padding(12)
        .foregroundStyle(.white)
        .background(color, in: RoundedRectangle(cornerRadius: 10))
    }

    @ViewBuilder
    private var hypothesisCard: some View {
        if let h = session.currentHypothesis {
            VStack(alignment: .leading, spacing: 6) {
                HStack {
                    Text("Hypothesis").font(.caption).foregroundStyle(.white.opacity(0.6))
                    Spacer()
                    Text("\(Int(h.confidence * 100))%")
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(confidenceColor(h.confidence))
                }
                Text(h.statement)
                    .font(.subheadline)
                    .foregroundStyle(.white)
                if let action = h.recommendedAction {
                    Text("→ \(action)")
                        .font(.caption)
                        .foregroundStyle(.white.opacity(0.8))
                }
            }
            .padding(12)
            .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 10))
        }
    }

    @ViewBuilder
    private var lastAssistantBubble: some View {
        if let last = session.messages.last(where: { $0.role == .assistant }) {
            HStack(alignment: .top, spacing: 8) {
                Image(systemName: "bubble.left.fill")
                    .foregroundStyle(.blue)
                Text(last.content)
                    .font(.callout)
                    .foregroundStyle(.white)
                    .lineLimit(3)
                Spacer()
            }
            .padding(10)
            .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 10))
        }
    }

    private func confidenceColor(_ c: Double) -> Color {
        if c >= 0.75 { return .green }
        if c >= 0.5 { return .yellow }
        return .orange
    }
}

#Preview {
    ZStack {
        Color.black.ignoresSafeArea()
        HUDOverlay(session: MockData.session).padding()
    }
}
