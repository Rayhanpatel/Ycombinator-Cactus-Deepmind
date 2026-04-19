import Foundation
import UIKit

struct PhotoAttachment: Identifiable, Sendable {
    let id: UUID
    let fileURL: URL

    init(id: UUID = UUID(), fileURL: URL) {
        self.id = id
        self.fileURL = fileURL
    }
}

final class PhotoAttachmentStore {
    private let fileManager = FileManager.default
    private let sessionDirectory: URL

    init() {
        let baseDirectory = (try? fileManager.url(
            for: .cachesDirectory,
            in: .userDomainMask,
            appropriateFor: nil,
            create: true
        )) ?? fileManager.temporaryDirectory

        sessionDirectory = baseDirectory
            .appendingPathComponent("ChatPhotoAttachments", isDirectory: true)
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
    }

    func persistPhoto(data: Data) throws -> PhotoAttachment {
        guard let image = UIImage(data: data) else {
            throw NSError(
                domain: "PhotoAttachmentStore",
                code: 1,
                userInfo: [NSLocalizedDescriptionKey: "The selected photo could not be decoded."]
            )
        }

        // Large camera originals slow down prompt ingestion without helping the chat sample.
        let preparedImage = image.scaledDown(maxDimension: 1536)

        guard let encodedImage = preparedImage.jpegData(compressionQuality: 0.85) else {
            throw NSError(
                domain: "PhotoAttachmentStore",
                code: 2,
                userInfo: [NSLocalizedDescriptionKey: "The selected photo could not be converted for Cactus."]
            )
        }

        try fileManager.createDirectory(at: sessionDirectory, withIntermediateDirectories: true, attributes: nil)

        let photoURL = sessionDirectory.appendingPathComponent("\(UUID().uuidString).jpg", isDirectory: false)
        try encodedImage.write(to: photoURL, options: [.atomic])

        return PhotoAttachment(fileURL: photoURL)
    }

    func discard(_ attachment: PhotoAttachment) {
        try? fileManager.removeItem(at: attachment.fileURL)
    }

    func resetSession() {
        guard fileManager.fileExists(atPath: sessionDirectory.path) else {
            return
        }

        try? fileManager.removeItem(at: sessionDirectory)
    }
}

private extension UIImage {
    func scaledDown(maxDimension: CGFloat) -> UIImage {
        let currentMaxDimension = max(size.width, size.height)
        guard currentMaxDimension > maxDimension else {
            return self
        }

        let scale = maxDimension / currentMaxDimension
        let targetSize = CGSize(width: size.width * scale, height: size.height * scale)
        let format = UIGraphicsImageRendererFormat.default()
        format.scale = 1

        return UIGraphicsImageRenderer(size: targetSize, format: format).image { _ in
            draw(in: CGRect(origin: .zero, size: targetSize))
        }
    }
}
