import SwiftUI

struct ToolCallBadge: View {
    let name: String
    let detail: String

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "wrench.and.screwdriver.fill")
                .font(.system(size: 10, weight: .bold))
                .foregroundStyle(AppTheme.accent.opacity(0.7))

            Text(name)
                .font(.system(size: 11, weight: .heavy, design: .monospaced))
                .foregroundStyle(AppTheme.accent.opacity(0.8))

            Text("•")
                .foregroundStyle(AppTheme.steel.opacity(0.5))

            Text(detail)
                .font(.caption2.weight(.medium))
                .foregroundStyle(AppTheme.mist.opacity(0.5))
                .lineLimit(1)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 7)
        .background(AppTheme.accent.opacity(0.06), in: Capsule())
        .overlay(Capsule().stroke(AppTheme.accent.opacity(0.10), lineWidth: 0.75))
        .frame(maxWidth: .infinity, alignment: .center)
    }
}

#Preview {
    ZStack {
        AppTheme.night.ignoresSafeArea()
        VStack(spacing: 10) {
            ToolCallBadge(name: "query_kb", detail: "Searching: capacitor failure Carrier 58STA")
            ToolCallBadge(name: "flag_safety", detail: "Electrical hazard detected")
            ToolCallBadge(name: "close_job", detail: "Generating resolution record")
        }
        .padding()
    }
}
