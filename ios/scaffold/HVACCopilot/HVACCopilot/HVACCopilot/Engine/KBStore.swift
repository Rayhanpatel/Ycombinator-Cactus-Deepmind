// KBStore.swift
// Loads the HVAC KB JSON files bundled with the app and serves
// keyword-scored retrieval for the query_kb tool. No embeddings —
// the 10-entry corpus is small enough that keyword overlap + term
// frequency beats the setup cost of MiniLM.
//
// Bundle requirement: add the repo's /kb folder to the Xcode project
// as a BLUE FOLDER REFERENCE with target membership HVACCopilot.
// At runtime, Bundle.main.url(forResource: "kb", withExtension: nil)
// returns that folder; we enumerate its .json children.

import Foundation

@MainActor
final class KBStore: ObservableObject {
    static let shared = KBStore()

    @Published private(set) var entries: [KBEntry] = []
    @Published private(set) var isLoaded: Bool = false
    @Published private(set) var loadError: String?

    private init() {
        load()
    }

    // MARK: - Load

    func load() {
        entries = []
        loadError = nil
        isLoaded = false

        guard let kbURL = Bundle.main.url(forResource: "kb", withExtension: nil) else {
            loadError = "kb/ folder not in app bundle — add as folder reference in Xcode."
            return
        }

        let decoder = JSONDecoder()
        var loaded: [KBEntry] = []
        let files = (try? FileManager.default.contentsOfDirectory(at: kbURL, includingPropertiesForKeys: nil)) ?? []
        for file in files where file.pathExtension == "json" {
            do {
                let data = try Data(contentsOf: file)
                let entry = try decoder.decode(KBEntry.self, from: data)
                loaded.append(entry)
            } catch {
                // Don't fail the whole load for one bad entry
                print("KBStore: skipped \(file.lastPathComponent): \(error)")
            }
        }

        entries = loaded.sorted(by: { $0.id < $1.id })
        isLoaded = true
    }

    // MARK: - Search

    /// Keyword-overlap scoring across symptom, diagnosis, and tags.
    /// Optionally narrows by equipment model substring.
    func search(query: String, equipmentModel: String? = nil, topK: Int = 3) -> [KBEntry] {
        let queryTerms = tokenize(query)
        guard !queryTerms.isEmpty else { return [] }

        let pool: [KBEntry]
        if let model = equipmentModel?.lowercased(), !model.isEmpty {
            pool = entries.filter { $0.model.lowercased().contains(model) || $0.brand.lowercased().contains(model) }
            // If model filter yields nothing, fall back to the full pool
            if pool.isEmpty { return search(query: query, topK: topK) }
        } else {
            pool = entries
        }

        let scored: [(KBEntry, Double)] = pool.map { entry in
            (entry, score(entry: entry, queryTerms: queryTerms))
        }
        return scored
            .filter { $0.1 > 0 }
            .sorted(by: { $0.1 > $1.1 })
            .prefix(topK)
            .map { $0.0 }
    }

    // MARK: - Scoring

    private func score(entry: KBEntry, queryTerms: Set<String>) -> Double {
        let symptomTerms = tokenize(entry.symptom)
        let diagnosisTerms = tokenize(entry.diagnosis)
        let tagTerms: Set<String> = entry.tags.map { Set($0.flatMap(tokenize)) } ?? []
        let brandModel = tokenize("\(entry.brand) \(entry.model)")

        // Weighted overlap: symptoms count most, then tags, then diagnosis, then brand/model.
        let symptomHits = Double(queryTerms.intersection(symptomTerms).count) * 3.0
        let tagHits = Double(queryTerms.intersection(tagTerms).count) * 2.5
        let diagnosisHits = Double(queryTerms.intersection(diagnosisTerms).count) * 1.5
        let brandHits = Double(queryTerms.intersection(brandModel).count) * 1.0
        return symptomHits + tagHits + diagnosisHits + brandHits
    }

    private func tokenize(_ text: String) -> Set<String> {
        let lowered = text.lowercased()
        let split = lowered.components(separatedBy: CharacterSet.alphanumerics.inverted)
        return Set(split.filter { $0.count >= 3 && !stopwords.contains($0) })
    }

    private let stopwords: Set<String> = [
        "the", "and", "for", "with", "this", "that", "from", "into", "but",
        "not", "any", "has", "are", "was", "were", "will", "can", "had",
        "unit", "system", "model"
    ]
}
