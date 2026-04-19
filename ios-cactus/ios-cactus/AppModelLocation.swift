import Foundation

enum AppModelLocation {
    struct Selection: Sendable {
        enum Source: Sendable {
            case bundled
            case applicationSupport
        }

        let source: Source
        let url: URL

        var description: String {
            switch source {
            case .bundled:
                return "Bundled model: \(url.path)"
            case .applicationSupport:
                return "Application Support model: \(url.path)"
            }
        }
    }

    static let setupHint = "Add the unzipped Gemma folder as a folder reference at ios-cactus/ios-cactus/Models/ or copy it under Library/Application Support/Models/."

    private static let preferredModelNames = [
        "gemma-4-e2b-it-int4-apple",
        "gemma-4-E2B-it-int4-apple",
        "gemma-4-e2b-it",
        "gemma-4-E2B-it",
        "gemma-4-e4b-it-int4-apple",
        "gemma-4-E4B-it-int4-apple",
        "gemma-4-e4b-it",
        "gemma-4-E4B-it",
    ]

    static func resolve() throws -> Selection {
        if let bundled = bundledSelection() {
            return bundled
        }

        if let appSupport = applicationSupportSelection() {
            return appSupport
        }

        throw NSError(
            domain: "AppModelLocation",
            code: 1,
            userInfo: [NSLocalizedDescriptionKey: "No Gemma model folder was found. \(setupHint)"]
        )
    }

    private static func bundledSelection() -> Selection? {
        guard let resourceURL = Bundle.main.resourceURL else {
            return nil
        }

        let modelsDirectory = resourceURL.appendingPathComponent("Models", isDirectory: true)
        guard let modelURL = bestModelURL(in: modelsDirectory) else {
            return nil
        }

        return Selection(source: .bundled, url: modelURL)
    }

    private static func applicationSupportSelection() -> Selection? {
        guard let base = try? FileManager.default.url(
            for: .applicationSupportDirectory,
            in: .userDomainMask,
            appropriateFor: nil,
            create: true
        ) else {
            return nil
        }

        let modelsDirectory = base.appendingPathComponent("Models", isDirectory: true)
        guard let modelURL = bestModelURL(in: modelsDirectory) else {
            return nil
        }

        return Selection(source: .applicationSupport, url: modelURL)
    }

    private static func bestModelURL(in directory: URL) -> URL? {
        guard let candidates = try? FileManager.default.contentsOfDirectory(
            at: directory,
            includingPropertiesForKeys: [.isDirectoryKey],
            options: [.skipsHiddenFiles]
        ) else {
            return nil
        }

        let directories = candidates.filter { url in
            (try? url.resourceValues(forKeys: [.isDirectoryKey]).isDirectory) == true
        }

        guard !directories.isEmpty else {
            return nil
        }

        return directories.sorted { lhs, rhs in
            let lhsScore = score(lhs)
            let rhsScore = score(rhs)

            if lhsScore == rhsScore {
                return lhs.lastPathComponent.localizedCaseInsensitiveCompare(rhs.lastPathComponent) == .orderedAscending
            }

            return lhsScore > rhsScore
        }.first
    }

    private static func score(_ url: URL) -> Int {
        let name = url.lastPathComponent.lowercased()
        var score = 0

        if preferredModelNames.contains(url.lastPathComponent) {
            score += 1000
        }
        if name.contains("e2b") {
            score += 300
        }
        if name.contains("e4b") {
            score += 200
        }
        if name.contains("int4") {
            score += 100
        }
        if name.contains("apple") {
            score += 50
        }
        if name.contains("gemma") {
            score += 25
        }

        return score
    }
}
