import SwiftUI

// MARK: - Enums

enum SessionStage: String {
    case idle = "Idle"
    case listening = "Listening"
    case assistantResponding = "Responding"
    case safetyAlert = "Safety Alert"
    case closeJobReview = "Close Job"
}

enum ModelState {
    case ready, listening, reasoning, review

    var title: String {
        switch self {
        case .ready: "Ready"
        case .listening: "Live mic"
        case .reasoning: "Reasoning"
        case .review: "Review"
        }
    }

    var tint: Color {
        switch self {
        case .ready: AppTheme.success
        case .listening: AppTheme.listening
        case .reasoning: AppTheme.accent
        case .review: AppTheme.caution
        }
    }
}

enum SafetyLevel {
    case clear, caution, stop

    var title: String {
        switch self {
        case .clear: "Clear"
        case .caution: "Watch"
        case .stop: "Stop"
        }
    }

    var tint: Color {
        switch self {
        case .clear: AppTheme.success
        case .caution: AppTheme.caution
        case .stop: AppTheme.danger
        }
    }
}

enum TranscriptSpeaker {
    case technician, assistant, system

    var title: String {
        switch self {
        case .technician: "Tech"
        case .assistant: "Copilot"
        case .system: "System"
        }
    }

    var tint: Color {
        switch self {
        case .technician: AppTheme.listening
        case .assistant: AppTheme.accent
        case .system: AppTheme.caution
        }
    }
}

// MARK: - Chat message types

enum ChatMessageKind {
    case text(speaker: TranscriptSpeaker, text: String)
    case hypothesis(MockHypothesis)
    case coaching(CoachingData)
    case finding(MockFinding)
    case toolCall(name: String, detail: String)
    case safetyAlert(level: SafetyLevel, message: String)
}

struct ChatMessage: Identifiable {
    let id = UUID()
    let kind: ChatMessageKind
}

struct CoachingData {
    let title: String
    let steps: [String]
}

struct MockFinding: Identifiable {
    let id = UUID()
    let title: String
    let location: String
    let severity: SafetyLevel
    let note: String
}

struct MockHypothesis {
    let title: String
    let confidence: Int
    let rationale: String
    let nextStep: String
}

struct CloseJobDraft {
    let diagnosis: String
    let fixApplied: String
    let partsUsed: [String]
    let timeOnSiteMinutes: Int
    let technicianNote: String
}

// MARK: - Scenario

struct OnSiteScenario: Identifiable {
    let id: String
    let name: String
    let jobLabel: String
    let equipmentLabel: String
    let stage: SessionStage
    let modelState: ModelState
    let safetyLevel: SafetyLevel
    let messages: [ChatMessage]
    let closeJobDraft: CloseJobDraft

    /// Convenience: extract findings from messages
    var findings: [MockFinding] {
        messages.compactMap {
            if case .finding(let f) = $0.kind { return f }
            return nil
        }
    }
}

// MARK: - Scenarios

enum PreviewScenarios {

    // MARK: 1 — Idle (tech just arrived)
    static let idleCarrier = OnSiteScenario(
        id: "carrier-idle",
        name: "Carrier idle walkthrough",
        jobLabel: "Job #2041 • Roof package unit",
        equipmentLabel: "Carrier 58STA090",
        stage: .idle,
        modelState: .ready,
        safetyLevel: .clear,
        messages: [
            ChatMessage(kind: .text(speaker: .system, text: "Session started. Point the camera at the unit.")),
            ChatMessage(kind: .text(speaker: .assistant, text: "Ready when you are. I can see the camera feed — describe the symptom and I'll start matching against the knowledge base.")),
        ],
        closeJobDraft: CloseJobDraft(
            diagnosis: "Awaiting technician walkthrough",
            fixApplied: "None yet",
            partsUsed: [],
            timeOnSiteMinutes: 0,
            technicianNote: "No close-out draft yet."
        )
    )

    // MARK: 2 — Listening (tech describing symptom)
    static let traneListening = OnSiteScenario(
        id: "trane-listening",
        name: "Trane active intake",
        jobLabel: "Job #2047 • Intermittent cooling",
        equipmentLabel: "Trane XR14 condenser",
        stage: .listening,
        modelState: .listening,
        safetyLevel: .clear,
        messages: [
            ChatMessage(kind: .text(speaker: .system, text: "Session started.")),
            ChatMessage(kind: .text(speaker: .assistant, text: "Camera feed active. Go ahead — what are you seeing?")),
            ChatMessage(kind: .text(speaker: .technician, text: "I'm hearing a chattering contactor and the fan pauses before the compressor drops out.")),
            ChatMessage(kind: .toolCall(name: "query_kb", detail: "Searching: chattering contactor, fan pause, compressor dropout")),
            ChatMessage(kind: .hypothesis(MockHypothesis(
                title: "Weak contactor coil",
                confidence: 62,
                rationale: "Audio symptoms and visible wiring wear suggest unstable pull-in on the contactor.",
                nextStep: "Inspect contactor face for pitting and confirm line voltage."
            ))),
            ChatMessage(kind: .text(speaker: .assistant, text: "Keep the disconnect and capacitor label in frame while I listen for more detail.")),
        ],
        closeJobDraft: CloseJobDraft(
            diagnosis: "Probable contactor failure",
            fixApplied: "Pending confirmation",
            partsUsed: ["Contactor 2-pole 40A"],
            timeOnSiteMinutes: 18,
            technicianNote: "Tech still collecting measurements."
        )
    )

    // MARK: 3 — Responding (main demo flow)
    static let carrierResponding = OnSiteScenario(
        id: "carrier-responding",
        name: "Carrier guided diagnosis",
        jobLabel: "Job #2054 • Clicking before shutoff",
        equipmentLabel: "Carrier 58STA120",
        stage: .assistantResponding,
        modelState: .reasoning,
        safetyLevel: .clear,
        messages: [
            ChatMessage(kind: .text(speaker: .system, text: "Session started. Camera and mic active.")),
            ChatMessage(kind: .text(speaker: .technician, text: "I'm seeing intermittent cooling on a Carrier 58STA with a clicking sound before shutoff.")),
            ChatMessage(kind: .toolCall(name: "query_kb", detail: "Matched: Carrier 58STA capacitor failure (3 prior cases)")),
            ChatMessage(kind: .hypothesis(MockHypothesis(
                title: "Failed run capacitor",
                confidence: 87,
                rationale: "Clicking before shutoff plus intermittent cooling strongly matches prior Carrier capacitor failures in the knowledge base.",
                nextStep: "Meter the capacitor and compare against the 45 µF rated value."
            ))),
            ChatMessage(kind: .text(speaker: .assistant, text: "Top match is a failed run capacitor — 45 µF, 370V. Two other techs reported the same pattern on this model.")),
            ChatMessage(kind: .coaching(CoachingData(
                title: "Verify & replace capacitor",
                steps: [
                    "Kill power at the disconnect",
                    "Remove the service panel",
                    "Discharge capacitor with insulated screwdriver",
                    "Photo the wire positions before disconnect",
                    "Meter capacitance — expect 45 µF ± 6%",
                    "Swap capacitor, match wire positions",
                    "Restore panel and power",
                    "Verify cooling: supply vent should read 15–20°F below return"
                ]
            ))),
            ChatMessage(kind: .text(speaker: .technician, text: "Capacitor's visibly bulged.")),
            ChatMessage(kind: .finding(MockFinding(
                title: "Capacitor bulge",
                location: "Electrical compartment",
                severity: .caution,
                note: "Can top visibly domed above normal profile."
            ))),
            ChatMessage(kind: .text(speaker: .assistant, text: "That confirms it. Swap it out, restore power, and verify supply vent is 15–20°F below return temp.")),
            ChatMessage(kind: .finding(MockFinding(
                title: "Loose spade connector",
                location: "Compressor lead",
                severity: .clear,
                note: "Connector seated but should be tightened during replacement."
            ))),
            ChatMessage(kind: .text(speaker: .assistant, text: "Log the capacitor dimensions when you swap it so the close-out record stays structured.")),
        ],
        closeJobDraft: CloseJobDraft(
            diagnosis: "Run capacitor out of spec",
            fixApplied: "Replace with matching 45/5 capacitor and secure spade connector",
            partsUsed: ["45/5 µF dual run capacitor", "Female spade connector"],
            timeOnSiteMinutes: 41,
            technicianNote: "Cooling restored after replacement and restart."
        )
    )

    // MARK: 4 — Safety alert
    static let safetyScenario = OnSiteScenario(
        id: "safety-alert",
        name: "Electrical safety stop",
        jobLabel: "Job #2062 • Service disconnect inspection",
        equipmentLabel: "Lennox rooftop gas pack",
        stage: .safetyAlert,
        modelState: .review,
        safetyLevel: .stop,
        messages: [
            ChatMessage(kind: .text(speaker: .system, text: "Session started.")),
            ChatMessage(kind: .text(speaker: .technician, text: "Opening the disconnect box now to check the wiring.")),
            ChatMessage(kind: .text(speaker: .assistant, text: "I can see the disconnect in frame. Proceeding with visual inspection.")),
            ChatMessage(kind: .toolCall(name: "flag_safety", detail: "Electrical hazard detected in camera feed")),
            ChatMessage(kind: .safetyAlert(
                level: .stop,
                message: "Exposed conductors near the disconnect. Kill power and verify lockout before touching the cabinet."
            )),
            ChatMessage(kind: .finding(MockFinding(
                title: "Exposed conductor",
                location: "Disconnect box",
                severity: .stop,
                note: "Insulation is split near the lug entry."
            ))),
            ChatMessage(kind: .finding(MockFinding(
                title: "Missing warning label",
                location: "Exterior panel",
                severity: .caution,
                note: "No visible lockout warning on access cover."
            ))),
            ChatMessage(kind: .text(speaker: .assistant, text: "Pause all troubleshooting. Confirm power is isolated before continuing.")),
        ],
        closeJobDraft: CloseJobDraft(
            diagnosis: "Electrical hazard present",
            fixApplied: "Escalate for immediate safe isolation and conductor repair",
            partsUsed: ["LOTO tag"],
            timeOnSiteMinutes: 12,
            technicianNote: "Work paused pending safe power isolation."
        )
    )

    // MARK: 5 — Close job
    static let closeJobScenario = OnSiteScenario(
        id: "close-job-review",
        name: "Close job summary",
        jobLabel: "Job #2054 • Cooling restored",
        equipmentLabel: "Carrier 58STA120",
        stage: .closeJobReview,
        modelState: .review,
        safetyLevel: .clear,
        messages: [
            ChatMessage(kind: .text(speaker: .system, text: "Session started. Camera and mic active.")),
            ChatMessage(kind: .text(speaker: .technician, text: "Intermittent cooling on a Carrier 58STA, clicking before shutoff.")),
            ChatMessage(kind: .toolCall(name: "query_kb", detail: "Matched: Carrier 58STA capacitor failure")),
            ChatMessage(kind: .hypothesis(MockHypothesis(
                title: "Failed run capacitor",
                confidence: 87,
                rationale: "Clicking + intermittent cooling matches 3 prior cases.",
                nextStep: "Meter capacitor against 45 µF rated value."
            ))),
            ChatMessage(kind: .text(speaker: .assistant, text: "Top match is a failed run capacitor.")),
            ChatMessage(kind: .text(speaker: .technician, text: "Capacitor is bulged. Swapping now.")),
            ChatMessage(kind: .finding(MockFinding(
                title: "Run capacitor replaced",
                location: "Electrical compartment",
                severity: .clear,
                note: "New 45/5 capacitor installed and leads reseated."
            ))),
            ChatMessage(kind: .text(speaker: .technician, text: "Done. Cooling at 38 at the vent, 25 minutes on site.")),
            ChatMessage(kind: .finding(MockFinding(
                title: "Restart verified",
                location: "System operation",
                severity: .clear,
                note: "Compressor and fan held through restart cycle."
            ))),
            ChatMessage(kind: .toolCall(name: "close_job", detail: "Generating structured resolution record")),
            ChatMessage(kind: .text(speaker: .assistant, text: "Close-out draft is ready. Diagnosis, parts, and time logged. Tap Close Job to review and export.")),
        ],
        closeJobDraft: CloseJobDraft(
            diagnosis: "Failed run capacitor causing intermittent cooling",
            fixApplied: "Replaced 45/5 dual run capacitor and tightened compressor lead",
            partsUsed: ["45/5 µF dual run capacitor", "1/4 in female spade connector"],
            timeOnSiteMinutes: 43,
            technicianNote: "Customer advised to monitor overnight cycle. First-time fix achieved."
        )
    )

    static let all: [OnSiteScenario] = [
        idleCarrier,
        traneListening,
        carrierResponding,
        safetyScenario,
        closeJobScenario
    ]

    static let initial = carrierResponding
}
