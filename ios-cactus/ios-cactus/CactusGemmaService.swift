import Foundation

struct LLMMessage: Codable, Sendable {
    let role: String
    let content: String
    let images: [String]?
    let audio: [String]?

    init(role: String, content: String, images: [String]? = nil, audio: [String]? = nil) {
        self.role = role
        self.content = content
        self.images = images
        self.audio = audio
    }
}

struct LLMResponse: Sendable {
    struct FunctionCall: Sendable {
        let name: String?
        let arguments: String?
    }

    let success: Bool
    let error: String?
    let cloudHandoff: Bool?
    let response: String?
    let functionCalls: [FunctionCall]?
    let timeToFirstTokenMs: Double?
    let totalTimeMs: Double?
    let prefillTps: Double?
    let decodeTps: Double?
    let ramUsageMb: Double?

    static func parse(_ rawJSON: String) throws -> LLMResponse {
        let data = Data(rawJSON.utf8)
        guard let payload = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw NSError(
                domain: "CactusGemmaService",
                code: 20,
                userInfo: [NSLocalizedDescriptionKey: "Cactus returned malformed JSON"]
            )
        }

        let functionCalls = (payload["function_calls"] as? [[String: Any]])?.map { item in
            FunctionCall(
                name: item["name"] as? String,
                arguments: item["arguments"] as? String
            )
        }

        return LLMResponse(
            success: payload["success"] as? Bool ?? false,
            error: payload["error"] as? String,
            cloudHandoff: payload["cloud_handoff"] as? Bool,
            response: payload["response"] as? String,
            functionCalls: functionCalls,
            timeToFirstTokenMs: payload["time_to_first_token_ms"] as? Double,
            totalTimeMs: payload["total_time_ms"] as? Double,
            prefillTps: payload["prefill_tps"] as? Double,
            decodeTps: payload["decode_tps"] as? Double,
            ramUsageMb: payload["ram_usage_mb"] as? Double
        )
    }
}

final class CactusGemmaService: @unchecked Sendable {
    private let queue = DispatchQueue(label: "ios-cactus.cactus-gemma-service")
    private var model: CactusModelT?

    func loadModel(at modelURL: URL) async throws {
        try await withCheckedThrowingContinuation { continuation in
            queue.async {
                do {
                    if let currentModel = self.model {
                        cactusDestroy(currentModel)
                        self.model = nil
                    }

                    cactusLogSetLevel(1)
                    self.model = try cactusInit(modelURL.path, nil, false)
                    continuation.resume()
                } catch {
                    continuation.resume(throwing: error)
                }
            }
        }
    }

    func generate(
        messages: [LLMMessage],
        onToken: @escaping @Sendable (String) -> Void
    ) async throws -> LLMResponse {
        try await withCheckedThrowingContinuation { continuation in
            queue.async {
                do {
                    guard let model = self.model else {
                        throw NSError(
                            domain: "CactusGemmaService",
                            code: 10,
                            userInfo: [NSLocalizedDescriptionKey: "Model is not loaded"]
                        )
                    }

                    cactusReset(model)

                    let messagesData = try JSONEncoder().encode(messages)
                    guard let messagesJSON = String(data: messagesData, encoding: .utf8) else {
                        throw NSError(
                            domain: "CactusGemmaService",
                            code: 11,
                            userInfo: [NSLocalizedDescriptionKey: "Failed to encode the prompt as UTF-8"]
                        )
                    }

                    let options: [String: Any] = [
                        "max_tokens": 256,
                        "temperature": 0.2,
                        "top_p": 0.9,
                        "auto_handoff": false,
                        "enable_thinking_if_supported": false,
                    ]

                    let optionsData = try JSONSerialization.data(withJSONObject: options)
                    guard let optionsJSON = String(data: optionsData, encoding: .utf8) else {
                        throw NSError(
                            domain: "CactusGemmaService",
                            code: 12,
                            userInfo: [NSLocalizedDescriptionKey: "Failed to encode generation options as UTF-8"]
                        )
                    }

                    let raw = try cactusComplete(model, messagesJSON, optionsJSON, nil) { token, _ in
                        onToken(token)
                    }

                    let decoded = try LLMResponse.parse(raw)
                    guard decoded.success else {
                        throw NSError(
                            domain: "CactusGemmaService",
                            code: 13,
                            userInfo: [NSLocalizedDescriptionKey: decoded.error ?? "Cactus returned an unknown error"]
                        )
                    }

                    continuation.resume(returning: decoded)
                } catch {
                    continuation.resume(throwing: error)
                }
            }
        }
    }
}
