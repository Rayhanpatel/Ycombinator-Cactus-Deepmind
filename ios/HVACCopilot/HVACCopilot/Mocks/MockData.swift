// MockData.swift
// Fixtures for SwiftUI previews and pre-spike UI development. Not shipped in demo mode.

import Foundation

enum MockData {
    static let session: SessionState = {
        var s = SessionState()
        s.messages = [
            Message(role: .system, content: "You are an HVAC field assistant."),
            Message(role: .user, content: "Unit is short cycling. Carrier 58STA090."),
            Message(role: .assistant, content: "Classic symptom. Check the run capacitor — common failure on the 58STA series. Point the camera at the outdoor unit's access panel.")
        ]
        s.findings = [
            Finding(
                location: "outdoor condenser access panel",
                issue: "run capacitor bulging at the top",
                severity: .major,
                partNumber: "P291-4554RS",
                notes: "45/5 uF dual-run. Measured 38 uF on the compressor side."
            )
        ]
        s.currentHypothesis = Hypothesis(
            statement: "Failed run capacitor causing compressor to trip on high amps after short run",
            confidence: 0.87,
            evidence: [
                "Visible bulge on capacitor top",
                "Measured 38 uF vs 45 uF rated",
                "Short cycling pattern consistent with compressor overload"
            ],
            recommendedAction: "Replace with P291-4554RS (stock 12 on truck)"
        )
        s.safetyLevel = .normal
        return s
    }()

    static let stopSafetySession: SessionState = {
        var s = session
        s.safetyLevel = .stop
        s.messages.append(Message(
            role: .assistant,
            content: "STOP. I'm detecting mercaptan in your audio. Suspected natural gas leak. Shut the main gas valve, ventilate, and evacuate if the smell intensifies."
        ))
        return s
    }()

    static let kbResults: [KBEntryPreview] = [
        .init(title: "Carrier 58STA — failed run capacitor", snippet: "Symptom: short cycling + clicking. Check 45/5 uF dual-run cap…"),
        .init(title: "Trane XR14 — pitted contactor", snippet: "Symptom: outdoor unit won't energize. Inspect 24V contactor for…"),
        .init(title: "Lennox ML180 — dirty flame sensor", snippet: "Symptom: furnace ignites then shuts off in ~5s. Remove flame sensor…")
    ]

    struct KBEntryPreview: Identifiable {
        let id = UUID()
        let title: String
        let snippet: String
    }
}
