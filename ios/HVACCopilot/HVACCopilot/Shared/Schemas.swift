// Schemas.swift
// FROZEN CONTRACT — do not edit without all 3 team members agreeing.
// This is the shared type surface between Engine, Views, and Tools.

import Foundation

// MARK: - Session

struct SessionState: Codable {
    var sessionId: String = UUID().uuidString
    var messages: [Message] = []
    var findings: [Finding] = []
    var currentHypothesis: Hypothesis?
    var safetyLevel: SafetyLevel = .normal
    var isListening: Bool = false
    var isThinking: Bool = false
}

// MARK: - Conversation

struct Message: Codable, Identifiable {
    let id: String
    let role: Role
    var content: String
    var timestamp: Date
    var imagePath: String?
    var audioPath: String?
    var toolCalls: [ToolCall]?

    init(role: Role, content: String, imagePath: String? = nil, audioPath: String? = nil, toolCalls: [ToolCall]? = nil) {
        self.id = UUID().uuidString
        self.role = role
        self.content = content
        self.timestamp = Date()
        self.imagePath = imagePath
        self.audioPath = audioPath
        self.toolCalls = toolCalls
    }

    enum Role: String, Codable {
        case system, user, assistant, tool
    }
}

struct ToolCall: Codable, Identifiable {
    let id: String
    let name: String
    let arguments: [String: AnyCodable]
    var result: String?
}

// MARK: - Domain

struct Finding: Codable, Identifiable {
    let id: String
    var location: String
    var issue: String
    var severity: Severity
    var partNumber: String?
    var notes: String?
    var timestamp: Date

    init(location: String, issue: String, severity: Severity, partNumber: String? = nil, notes: String? = nil) {
        self.id = UUID().uuidString
        self.location = location
        self.issue = issue
        self.severity = severity
        self.partNumber = partNumber
        self.notes = notes
        self.timestamp = Date()
    }

    enum Severity: String, Codable, CaseIterable {
        case info
        case minor
        case major
        case critical
    }
}

struct Hypothesis: Codable, Identifiable {
    let id: String
    var statement: String
    var confidence: Double // 0.0 - 1.0
    var evidence: [String]
    var recommendedAction: String?

    init(statement: String, confidence: Double, evidence: [String] = [], recommendedAction: String? = nil) {
        self.id = UUID().uuidString
        self.statement = statement
        self.confidence = confidence
        self.evidence = evidence
        self.recommendedAction = recommendedAction
    }
}

enum SafetyLevel: String, Codable {
    case normal
    case caution
    case stop
}

// MARK: - AnyCodable (tool arguments accept heterogeneous JSON values)

struct AnyCodable: Codable {
    let value: Any

    init(_ value: Any) { self.value = value }

    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if let b = try? c.decode(Bool.self) { value = b; return }
        if let i = try? c.decode(Int.self) { value = i; return }
        if let d = try? c.decode(Double.self) { value = d; return }
        if let s = try? c.decode(String.self) { value = s; return }
        if let a = try? c.decode([AnyCodable].self) { value = a.map { $0.value }; return }
        if let o = try? c.decode([String: AnyCodable].self) { value = o.mapValues { $0.value }; return }
        value = NSNull()
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch value {
        case let b as Bool: try c.encode(b)
        case let i as Int: try c.encode(i)
        case let d as Double: try c.encode(d)
        case let s as String: try c.encode(s)
        case let a as [Any]: try c.encode(a.map(AnyCodable.init))
        case let o as [String: Any]: try c.encode(o.mapValues(AnyCodable.init))
        default: try c.encodeNil()
        }
    }
}
