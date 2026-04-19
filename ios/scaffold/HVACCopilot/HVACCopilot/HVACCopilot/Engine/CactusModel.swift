// CactusModel.swift
// Thin wrapper around the Cactus Swift SDK. One actor owns model lifecycle.
// API surface used:
//   cactusInit(modelPath, nil, false) -> OpaquePointer
//   cactusComplete(model, messagesJSON, optionsJSON, toolsJSON, callback) -> resultJSON

import Foundation
import cactus

actor CactusModel {
    static let shared = CactusModel()

    private var model: OpaquePointer?
    private(set) var isLoaded: Bool = false
    private(set) var lastError: String?

    private init() {}

    // MARK: - Load

    /// Loads Gemma 4 E4B from the app bundle. Bundle folder name: `gemma-4-E4B-it`.
    func load() async throws {
        guard !isLoaded else { return }

        guard let bundlePath = Bundle.main.path(forResource: "gemma-4-E4B-it", ofType: nil) else {
            let msg = "Model folder 'gemma-4-E4B-it' not found in app bundle. See README step 4."
            lastError = msg
            throw CactusError.modelMissing(msg)
        }

        do {
            self.model = try cactusInit(bundlePath, nil, false)
            self.isLoaded = true
        } catch {
            lastError = String(describing: error)
            throw CactusError.initFailed(lastError ?? "unknown")
        }
    }

    // MARK: - Complete

    /// Runs a completion against the loaded model.
    /// - Parameters:
    ///   - messages: array of role/content dicts (+ optional "images", "audio" file paths)
    ///   - tools: array of OpenAI-format tool schemas, or nil
    /// - Returns: decoded response JSON as [String: Any]
    func complete(messages: [[String: Any]], tools: [[String: Any]]? = nil) async throws -> [String: Any] {
        guard isLoaded, let model = model else {
            throw CactusError.notLoaded
        }

        let messagesJSON = try jsonString(messages)
        let toolsJSON = tools.map { (try? jsonString($0)) ?? "[]" }

        let resultJSON: String
        do {
            resultJSON = try cactusComplete(model, messagesJSON, nil, toolsJSON, nil)
        } catch {
            throw CactusError.completeFailed(String(describing: error))
        }

        guard let data = resultJSON.data(using: .utf8),
              let obj = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw CactusError.badResponse(resultJSON)
        }
        return obj
    }

    /// Convenience: send a single user message as text, get back the assistant's text reply.
    func completeText(_ userText: String) async throws -> String {
        let messages: [[String: Any]] = [
            ["role": "system", "content": "You are an HVAC field assistant. Be concise and technical."],
            ["role": "user", "content": userText]
        ]
        let response = try await complete(messages: messages)
        return extractAssistantText(from: response) ?? "(no text in response)"
    }

    // MARK: - Helpers

    private func jsonString(_ value: Any) throws -> String {
        let data = try JSONSerialization.data(withJSONObject: value, options: [])
        return String(data: data, encoding: .utf8) ?? "[]"
    }

    private func extractAssistantText(from response: [String: Any]) -> String? {
        // Cactus response shape (per docs): { "choices": [{ "message": { "role": "assistant", "content": "..." } }] }
        if let choices = response["choices"] as? [[String: Any]],
           let first = choices.first,
           let message = first["message"] as? [String: Any],
           let content = message["content"] as? String {
            return content
        }
        // Fallback: some builds return { "content": "..." }
        if let content = response["content"] as? String { return content }
        return nil
    }
}

enum CactusError: Error, LocalizedError {
    case modelMissing(String)
    case initFailed(String)
    case notLoaded
    case completeFailed(String)
    case badResponse(String)

    var errorDescription: String? {
        switch self {
        case .modelMissing(let s): return "Model missing: \(s)"
        case .initFailed(let s): return "cactusInit failed: \(s)"
        case .notLoaded: return "Model not loaded yet"
        case .completeFailed(let s): return "cactusComplete failed: \(s)"
        case .badResponse(let s): return "Bad model response: \(s.prefix(200))"
        }
    }
}
