// OnSiteView.swift
// Main on-site screen (post-spike). Camera preview placeholder + HUD overlay + listening indicator.
// Person 2: iterate here. Camera wiring comes T+4h; keep the placeholder for now.

import SwiftUI

struct OnSiteView: View {
    @State var session: SessionState

    var body: some View {
        ZStack(alignment: .top) {
            cameraPlaceholder
                .ignoresSafeArea()

            VStack {
                HUDOverlay(session: session)
                Spacer()
                controlBar
            }
            .padding()
        }
        .preferredColorScheme(.dark)
    }

    private var cameraPlaceholder: some View {
        LinearGradient(
            colors: [Color(white: 0.08), Color(white: 0.18)],
            startPoint: .top,
            endPoint: .bottom
        )
        .overlay(
            VStack {
                Image(systemName: "camera.viewfinder")
                    .font(.system(size: 64))
                    .foregroundStyle(.white.opacity(0.25))
                Text("Camera preview (wire up T+4h)")
                    .font(.caption)
                    .foregroundStyle(.white.opacity(0.4))
            }
        )
    }

    private var controlBar: some View {
        HStack(spacing: 24) {
            NavigationLink {
                FindingsList(findings: session.findings)
            } label: {
                Label("\(session.findings.count)", systemImage: "list.clipboard.fill")
                    .padding(.horizontal, 14).padding(.vertical, 10)
                    .background(.thinMaterial, in: Capsule())
            }

            Button(action: { session.isListening.toggle() }) {
                Image(systemName: session.isListening ? "mic.fill" : "mic.slash.fill")
                    .font(.system(size: 28))
                    .foregroundStyle(.white)
                    .frame(width: 72, height: 72)
                    .background(session.isListening ? Color.red : Color.blue, in: Circle())
            }

            NavigationLink {
                CloseJobView(session: session)
            } label: {
                Label("Close", systemImage: "checkmark.seal.fill")
                    .padding(.horizontal, 14).padding(.vertical, 10)
                    .background(.thinMaterial, in: Capsule())
            }
        }
        .foregroundStyle(.white)
    }
}

#Preview("Normal") {
    NavigationStack { OnSiteView(session: MockData.session) }
}

#Preview("Safety STOP") {
    NavigationStack { OnSiteView(session: MockData.stopSafetySession) }
}
