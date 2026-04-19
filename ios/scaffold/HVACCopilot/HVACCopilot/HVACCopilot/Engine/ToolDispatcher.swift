// ToolDispatcher.swift
// Parses tool_calls from a Cactus chat completion response, runs
// handlers against our stores, and builds tool-role messages to
// append to the conversation. The returned messages go back to
// Gemma 4 for a follow-up turn that speaks the final answer to
// the tech.
//
// Expected response shape from cactusComplete:
//   {
//     "choices": [{
//       "message": {
//         "role": "assistant",
//         "content": "...",
//         "tool_calls": [
//           {"id": "call_1", "type": "function",
//            "function": {"name": "query_kb", "arguments": "{\"query\":\"...\"}"}}
//         ]
//       }
//     }]
//   }

import Foundation

@MainActor
struct ToolDispatcher {
    let kb: KBStore
    let findings: FindingsStore

    init(kb: KBStore = .shared, findings: FindingsStore = .shared) {
        self.kb = kb
        self.findings = findings
    }

    // MARK: - Entry

    /// Extracts tool_calls from a decoded Cactus response and runs each.
    /// Returns an array of tool-role messages ready to append and send
    /// back to the model on the next turn.
    func dispatch(response: [String: Any]) -> [Message] {
        let calls = extractToolCalls(from: response)
        return calls.map { call in
            let result = run(call)
            return Message(role: .tool, content: result, toolCalls: nil)
        }
    }

    // MARK: - Extract

    private func extractToolCalls(from response: [String: Any]) -> [(id: String, name: String, arguments: [String: Any])] {
        guard let choices = response["choices"] as? [[String: Any]],
              let first = choices.first,
              let message = first["message"] as? [String: Any],
              let rawCalls = message["tool_calls"] as? [[String: Any]]
        else { return [] }

        return rawCalls.compactMap { raw in
            guard let id = raw["id"] as? String,
                  let function = raw["function"] as? [String: Any],
                  let name = function["name"] as? String
            else { return nil }
            let argsString = (function["arguments"] as? String) ?? "{}"
            let argsData = argsString.data(using: .utf8) ?? Data()
            let args = (try? JSONSerialization.jsonObject(with: argsData) as? [String: Any]) ?? [:]
            return (id: id, name: name, arguments: args)
        }
    }

    // MARK: - Run

    private func run(_ call: (id: String, name: String, arguments: [String: Any])) -> String {
        switch call.name {
        case "query_kb": return runQueryKB(call.arguments)
        case "log_finding": return runLogFinding(call.arguments)
        case "flag_safety": return runFlagSafety(call.arguments)
        case "flag_scope_change": return runFlagScopeChange(call.arguments)
        case "close_job": return runCloseJob(call.arguments)
        default:
            return jsonString(["error": "unknown tool: \(call.name)"])
        }
    }

    // MARK: - Handlers

    private func runQueryKB(_ args: [String: Any]) -> String {
        let query = (args["query"] as? String) ?? ""
        let model = args["equipment_model"] as? String
        let topK = (args["top_k"] as? Int) ?? 3

        let hits = kb.search(query: query, equipmentModel: model, topK: topK)
        let payload: [String: Any] = [
            "query": query,
            "hits": hits.map { entry -> [String: Any] in
                [
                    "id": entry.id,
                    "brand": entry.brand,
                    "model": entry.model,
                    "symptom": entry.symptom,
                    "diagnosis": entry.diagnosis,
                    "part_number": entry.partNumber as Any,
                    "procedure": entry.procedure,
                    "safety_notes": entry.safetyNotes as Any
                ]
            }
        ]
        return jsonString(payload)
    }

    private func runLogFinding(_ args: [String: Any]) -> String {
        let location = (args["location"] as? String) ?? "unspecified"
        let issue = (args["issue"] as? String) ?? "unspecified"
        let severityStr = (args["severity"] as? String) ?? "info"
        let severity = Finding.Severity(rawValue: severityStr) ?? .info
        let partNumber = args["part_number"] as? String
        let notes = args["notes"] as? String

        let finding = Finding(
            location: location,
            issue: issue,
            severity: severity,
            partNumber: partNumber,
            notes: notes
        )
        findings.add(finding)
        return jsonString([
            "ok": true,
            "finding_id": finding.id,
            "logged": "\(severity.rawValue): \(issue) at \(location)"
        ])
    }

    private func runFlagSafety(_ args: [String: Any]) -> String {
        let hazard = (args["hazard"] as? String) ?? "unspecified hazard"
        let action = (args["immediate_action"] as? String) ?? "Stop work. Contact supervisor."
        let levelStr = (args["level"] as? String) ?? "stop"
        let level: SafetyLevel = (levelStr == "caution") ? .caution : .stop

        findings.raiseSafety(level: level, message: "\(hazard). \(action)")
        return jsonString([
            "ok": true,
            "level": level.rawValue,
            "hazard": hazard,
            "immediate_action": action
        ])
    }

    private func runFlagScopeChange(_ args: [String: Any]) -> String {
        let original = (args["original_scope"] as? String) ?? ""
        let new = (args["new_scope"] as? String) ?? ""
        let reason = (args["reason"] as? String) ?? ""
        let extra = args["estimated_extra_time_minutes"] as? Int

        let change = ScopeChange(
            originalScope: original,
            newScope: new,
            reason: reason,
            estimatedExtraMinutes: extra
        )
        findings.proposeScopeChange(change)
        return jsonString([
            "ok": true,
            "scope_change_id": change.id,
            "awaiting_approval": true
        ])
    }

    private func runCloseJob(_ args: [String: Any]) -> String {
        let summary = (args["summary"] as? String) ?? ""
        let parts = (args["parts_used"] as? [String]) ?? []
        let followUp = (args["follow_up_required"] as? Bool) ?? false
        let followUpNotes = args["follow_up_notes"] as? String

        let closure = JobClosure(
            summary: summary,
            partsUsed: parts,
            followUpRequired: followUp,
            followUpNotes: followUpNotes
        )
        findings.close(closure)
        return jsonString([
            "ok": true,
            "closed": true,
            "summary": summary,
            "parts_count": parts.count
        ])
    }

    // MARK: - JSON helper

    private func jsonString(_ obj: [String: Any]) -> String {
        let sanitized = sanitizeForJSON(obj)
        guard let data = try? JSONSerialization.data(withJSONObject: sanitized, options: []),
              let s = String(data: data, encoding: .utf8)
        else { return "{}" }
        return s
    }

    /// JSONSerialization rejects NSNull inside Any; convert .none and
    /// arbitrary optionals into NSNull explicitly.
    private func sanitizeForJSON(_ value: Any) -> Any {
        if let dict = value as? [String: Any] {
            return dict.mapValues { sanitizeForJSON($0) }
        }
        if let arr = value as? [Any] {
            return arr.map { sanitizeForJSON($0) }
        }
        let mirror = Mirror(reflecting: value)
        if mirror.displayStyle == .optional {
            if mirror.children.count == 0 { return NSNull() }
            return sanitizeForJSON(mirror.children.first!.value)
        }
        return value
    }
}
