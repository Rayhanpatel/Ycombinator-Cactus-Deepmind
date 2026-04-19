// FindingsStore.swift
// Observable in-memory store for the current session's findings,
// safety level, proposed scope changes, and final closure. Simple
// on purpose — swap to SQLite post-MVP if we need persistence
// across app launches. For the demo, a single session is enough.

import Foundation
import Combine

@MainActor
final class FindingsStore: ObservableObject {
    static let shared = FindingsStore()

    @Published var findings: [Finding] = []
    @Published var safetyLevel: SafetyLevel = .normal
    @Published var safetyMessage: String?
    @Published var pendingScopeChanges: [ScopeChange] = []
    @Published var lastClosure: JobClosure?

    private init() {}

    // MARK: - Findings

    func add(_ finding: Finding) {
        findings.append(finding)
    }

    // MARK: - Safety

    func raiseSafety(level: SafetyLevel, message: String) {
        safetyLevel = level
        safetyMessage = message
    }

    func clearSafety() {
        safetyLevel = .normal
        safetyMessage = nil
    }

    // MARK: - Scope changes

    func proposeScopeChange(_ change: ScopeChange) {
        pendingScopeChanges.append(change)
    }

    func approveScopeChange(id: String) {
        guard let idx = pendingScopeChanges.firstIndex(where: { $0.id == id }) else { return }
        pendingScopeChanges[idx].approved = true
    }

    func rejectScopeChange(id: String) {
        pendingScopeChanges.removeAll { $0.id == id }
    }

    // MARK: - Closure

    func close(_ closure: JobClosure) {
        lastClosure = closure
    }

    // MARK: - Session reset

    func resetSession() {
        findings = []
        safetyLevel = .normal
        safetyMessage = nil
        pendingScopeChanges = []
        lastClosure = nil
    }
}
