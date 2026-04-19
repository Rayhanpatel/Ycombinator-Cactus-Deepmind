import SwiftUI

enum SessionStage: String {
    case idle = "Idle"
    case listening = "Listening"
    case assistantResponding = "Responding"
    case safetyAlert = "Safety Alert"
    case closeJobReview = "Close Job"
}

enum ModelState {
    case ready
    case listening
    case reasoning
    case review

    var title: String {
        switch self {
        case .ready:
            "Ready"
        case .listening:
            "Live mic"
        case .reasoning:
            "Reasoning"
        case .review:
            "Review"
        }
    }

    var tint: Color {
        switch self {
        case .ready:
            AppTheme.success
        case .listening:
            AppTheme.listening
        case .reasoning:
            AppTheme.accent
        case .review:
            AppTheme.caution
        }
    }
}

enum SafetyLevel {
    case clear
    case caution
    case stop

    var title: String {
        switch self {
        case .clear:
            "Clear"
        case .caution:
            "Watch"
        case .stop:
            "Stop"
        }
    }

    var tint: Color {
        switch self {
        case .clear:
            AppTheme.success
        case .caution:
            AppTheme.caution
        case .stop:
            AppTheme.danger
        }
    }
}

enum TranscriptSpeaker {
    case technician
    case assistant
    case system

    var title: String {
        switch self {
        case .technician:
            "Tech"
        case .assistant:
            "Copilot"
        case .system:
            "System"
        }
    }

    var tint: Color {
        switch self {
        case .technician:
            AppTheme.listening
        case .assistant:
            AppTheme.accent
        case .system:
            AppTheme.caution
        }
    }
}

struct TranscriptLine: Identifiable {
    let id = UUID()
    let speaker: TranscriptSpeaker
    let text: String
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

struct OnSiteScenario: Identifiable {
    let id: String
    let name: String
    let jobLabel: String
    let equipmentLabel: String
    let sceneLabel: String
    let stage: SessionStage
    let modelState: ModelState
    let safetyLevel: SafetyLevel
    let safetyMessage: String?
    let transcriptLines: [TranscriptLine]
    let hypothesis: MockHypothesis?
    let findings: [MockFinding]
    let closeJobDraft: CloseJobDraft
    let transcriptFooter: String
}

enum PreviewScenarios {
    static let idleCarrier = OnSiteScenario(
        id: "carrier-idle",
        name: "Carrier idle walkthrough",
        jobLabel: "Job #2041 • Roof package unit",
        equipmentLabel: "Carrier 58STA090",
        sceneLabel: "Return grille, service panel in frame",
        stage: .idle,
        modelState: .ready,
        safetyLevel: .clear,
        safetyMessage: nil,
        transcriptLines: [
            TranscriptLine(speaker: .system, text: "System ready. Point the camera at the unit and begin when the tech is in place."),
            TranscriptLine(speaker: .assistant, text: "I can track findings, surface the top hypothesis, and prep the close-out summary.")
        ],
        hypothesis: nil,
        findings: [],
        closeJobDraft: CloseJobDraft(
            diagnosis: "Awaiting technician walkthrough",
            fixApplied: "None yet",
            partsUsed: [],
            timeOnSiteMinutes: 0,
            technicianNote: "No close-out draft yet."
        ),
        transcriptFooter: "Idle state for first-screen review"
    )

    static let traneListening = OnSiteScenario(
        id: "trane-listening",
        name: "Trane active intake",
        jobLabel: "Job #2047 • Intermittent cooling",
        equipmentLabel: "Trane XR14 condenser",
        sceneLabel: "Condenser fan centered, wiring compartment visible",
        stage: .listening,
        modelState: .listening,
        safetyLevel: .clear,
        safetyMessage: nil,
        transcriptLines: [
            TranscriptLine(speaker: .technician, text: "I’m hearing a chattering contactor and the fan pauses before the compressor drops out."),
            TranscriptLine(speaker: .assistant, text: "Listening for symptom details. Keep the disconnect and capacitor label in frame.")
        ],
        hypothesis: MockHypothesis(
            title: "Weak contactor coil",
            confidence: 62,
            rationale: "Audio symptoms and visible wiring wear both suggest unstable pull-in on the contactor.",
            nextStep: "Inspect contactor face for pitting and confirm line voltage before replacement."
        ),
        findings: [
            MockFinding(
                title: "Pitted contact face",
                location: "Contactor compartment",
                severity: .caution,
                note: "Surface pitting visible on the moving contact."
            )
        ],
        closeJobDraft: CloseJobDraft(
            diagnosis: "Probable contactor failure",
            fixApplied: "Pending confirmation",
            partsUsed: ["Contactor 2-pole 40A"],
            timeOnSiteMinutes: 18,
            technicianNote: "Tech still collecting measurements."
        ),
        transcriptFooter: "Listening state with live hypothesis"
    )

    static let carrierResponding = OnSiteScenario(
        id: "carrier-responding",
        name: "Carrier guided diagnosis",
        jobLabel: "Job #2054 • Clicking before shutoff",
        equipmentLabel: "Carrier 58STA120",
        sceneLabel: "Blower cabinet open, run capacitor label visible",
        stage: .assistantResponding,
        modelState: .reasoning,
        safetyLevel: .clear,
        safetyMessage: nil,
        transcriptLines: [
            TranscriptLine(speaker: .technician, text: "I’m seeing intermittent cooling on a Carrier 58STA with a clicking sound before shutoff."),
            TranscriptLine(speaker: .assistant, text: "Top match is a failed run capacitor. Check for bulging and verify capacitance against the 45 microfarad label."),
            TranscriptLine(speaker: .assistant, text: "Log the capacitor dimensions if you swap it so the close-out stays structured.")
        ],
        hypothesis: MockHypothesis(
            title: "Failed run capacitor",
            confidence: 87,
            rationale: "The symptom pair of clicking before shutoff plus intermittent cooling strongly matches prior Carrier capacitor failures.",
            nextStep: "Meter the capacitor, compare against rated value, then inspect for bulging or leaking."
        ),
        findings: [
            MockFinding(
                title: "Capacitor bulge",
                location: "Electrical compartment",
                severity: .caution,
                note: "Can top visibly domed above normal profile."
            ),
            MockFinding(
                title: "Loose spade connector",
                location: "Compressor lead",
                severity: .clear,
                note: "Connector seated but should be tightened during replacement."
            )
        ],
        closeJobDraft: CloseJobDraft(
            diagnosis: "Run capacitor out of spec",
            fixApplied: "Replace with matching 45/5 capacitor and secure spade connector",
            partsUsed: ["45/5 uF dual run capacitor", "Female spade connector"],
            timeOnSiteMinutes: 41,
            technicianNote: "Cooling restored after replacement and restart."
        ),
        transcriptFooter: "Assistant response state for the main demo flow"
    )

    static let safetyScenario = OnSiteScenario(
        id: "safety-alert",
        name: "Electrical safety stop",
        jobLabel: "Job #2062 • Service disconnect inspection",
        equipmentLabel: "Lennox rooftop gas pack",
        sceneLabel: "Disconnect box open, exposed conductors in view",
        stage: .safetyAlert,
        modelState: .review,
        safetyLevel: .stop,
        safetyMessage: "Safety stop: exposed conductors near the disconnect. Kill power and verify lockout before touching the cabinet.",
        transcriptLines: [
            TranscriptLine(speaker: .system, text: "Tool event: `flag_safety` raised for electrical hazard."),
            TranscriptLine(speaker: .assistant, text: "Pause troubleshooting. Confirm power is isolated before the walkthrough continues.")
        ],
        hypothesis: nil,
        findings: [
            MockFinding(
                title: "Exposed conductor",
                location: "Disconnect box",
                severity: .stop,
                note: "Insulation is split near the lug entry."
            ),
            MockFinding(
                title: "Missing warning label",
                location: "Exterior panel",
                severity: .caution,
                note: "No visible lockout warning on access cover."
            )
        ],
        closeJobDraft: CloseJobDraft(
            diagnosis: "Electrical hazard present",
            fixApplied: "Escalate for immediate safe isolation and conductor repair",
            partsUsed: ["LOTO tag"],
            timeOnSiteMinutes: 12,
            technicianNote: "Work paused pending safe power isolation."
        ),
        transcriptFooter: "Safety interrupt review"
    )

    static let closeJobScenario = OnSiteScenario(
        id: "close-job-review",
        name: "Close job summary",
        jobLabel: "Job #2054 • Cooling restored",
        equipmentLabel: "Carrier 58STA120",
        sceneLabel: "Post-repair unit with panel reinstalled",
        stage: .closeJobReview,
        modelState: .review,
        safetyLevel: .clear,
        safetyMessage: nil,
        transcriptLines: [
            TranscriptLine(speaker: .assistant, text: "Close-out draft is ready. Confirm diagnosis, parts, and total time on site."),
            TranscriptLine(speaker: .technician, text: "Cooling is stable now. Lock in the capacitor replacement and first-time fix.")
        ],
        hypothesis: MockHypothesis(
            title: "Repair complete",
            confidence: 94,
            rationale: "Follow-up response and stable cooling indicate the initial diagnosis resolved the issue.",
            nextStep: "Review the summary sheet, then export the resolution record."
        ),
        findings: [
            MockFinding(
                title: "Run capacitor replaced",
                location: "Electrical compartment",
                severity: .clear,
                note: "New 45/5 capacitor installed and leads reseated."
            ),
            MockFinding(
                title: "Restart verified",
                location: "System operation",
                severity: .clear,
                note: "Compressor and fan held through restart cycle."
            )
        ],
        closeJobDraft: CloseJobDraft(
            diagnosis: "Failed run capacitor causing intermittent cooling",
            fixApplied: "Replaced 45/5 dual run capacitor and tightened compressor lead connection",
            partsUsed: ["45/5 uF dual run capacitor", "1/4 in female spade connector"],
            timeOnSiteMinutes: 43,
            technicianNote: "Customer advised to monitor overnight cycle. First-time fix achieved."
        ),
        transcriptFooter: "Review sheet state"
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
