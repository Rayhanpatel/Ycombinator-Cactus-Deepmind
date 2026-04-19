import SwiftUI

struct ChatBubbleView: View {
    let speaker: TranscriptSpeaker
    let text: String

    var body: some View {
        HStack(alignment: .top, spacing: 0) {
            if speaker == .technician { Spacer(minLength: 48) }

            VStack(alignment: speaker == .technician ? .trailing : .leading, spacing: 4) {
                // Speaker label
                Text(speaker.title.uppercased())
                    .font(.system(size: 9, weight: .heavy))
                    .tracking(0.6)
                    .foregroundStyle(speaker.tint.opacity(0.8))

                // Bubble
                Text(text)
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(speaker == .technician ? .white : AppTheme.mist.opacity(0.92))
                    .padding(.horizontal, 14)
                    .padding(.vertical, 10)
                    .background(bubbleColor, in: BubbleShape(isFromUser: speaker == .technician))
            }

            if speaker != .technician { Spacer(minLength: 48) }
        }
    }

    private var bubbleColor: Color {
        switch speaker {
        case .technician:
            return AppTheme.listening.opacity(0.18)
        case .assistant:
            return AppTheme.accent.opacity(0.12)
        case .system:
            return Color.white.opacity(0.06)
        }
    }
}

private struct BubbleShape: Shape {
    let isFromUser: Bool

    func path(in rect: CGRect) -> Path {
        let r: CGFloat = 16
        let smallR: CGFloat = 4
        return RoundedCornerShape(
            topLeft: r,
            topRight: r,
            bottomLeft: isFromUser ? r : smallR,
            bottomRight: isFromUser ? smallR : r
        ).path(in: rect)
    }
}

private struct RoundedCornerShape: Shape {
    let topLeft: CGFloat
    let topRight: CGFloat
    let bottomLeft: CGFloat
    let bottomRight: CGFloat

    func path(in rect: CGRect) -> Path {
        var path = Path()
        let w = rect.width, h = rect.height

        path.move(to: CGPoint(x: topLeft, y: 0))
        path.addLine(to: CGPoint(x: w - topRight, y: 0))
        path.addArc(tangent1End: CGPoint(x: w, y: 0), tangent2End: CGPoint(x: w, y: topRight), radius: topRight)
        path.addLine(to: CGPoint(x: w, y: h - bottomRight))
        path.addArc(tangent1End: CGPoint(x: w, y: h), tangent2End: CGPoint(x: w - bottomRight, y: h), radius: bottomRight)
        path.addLine(to: CGPoint(x: bottomLeft, y: h))
        path.addArc(tangent1End: CGPoint(x: 0, y: h), tangent2End: CGPoint(x: 0, y: h - bottomLeft), radius: bottomLeft)
        path.addLine(to: CGPoint(x: 0, y: topLeft))
        path.addArc(tangent1End: CGPoint(x: 0, y: 0), tangent2End: CGPoint(x: topLeft, y: 0), radius: topLeft)

        return path
    }
}

#Preview {
    ZStack {
        AppTheme.night.ignoresSafeArea()
        VStack(spacing: 10) {
            ChatBubbleView(speaker: .technician, text: "I'm seeing intermittent cooling on a Carrier 58STA with a clicking sound before shutoff.")
            ChatBubbleView(speaker: .assistant, text: "Top match is a failed run capacitor. Check for bulging and verify capacitance against the 45 µF label.")
            ChatBubbleView(speaker: .system, text: "Session started.")
        }
        .padding()
    }
}
