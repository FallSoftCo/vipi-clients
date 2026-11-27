import Foundation
import ImageIO
import UniformTypeIdentifiers

/// Only the sender's authenticated Signal payload carries this self-issued update.
struct PrivateProfileAvatar: Codable, Equatable {
    let revision: Int64
    let jpeg: Data?
    private enum CodingKeys: String, CodingKey { case revision, jpeg }
    init(revision: Int64, jpeg: Data?) throws {
        guard revision > 0 else { throw MessageJournal.Failure.invalidMessage }
        if let jpeg {
            guard (1...4096).contains(jpeg.count),
                let src = CGImageSourceCreateWithData(jpeg as CFData, nil),
                CGImageSourceGetType(src) as String? == UTType.jpeg.identifier,
                let props = CGImageSourceCopyPropertiesAtIndex(src, 0, nil) as? [CFString: Any],
                props[kCGImagePropertyPixelWidth] as? Int == 96,
                props[kCGImagePropertyPixelHeight] as? Int == 96,
                CGImageSourceCreateImageAtIndex(src, 0, nil) != nil
            else { throw MessageJournal.Failure.invalidMessage }
        }
        self.revision = revision
        self.jpeg = jpeg
    }
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        guard c.contains(.jpeg) else { throw MessageJournal.Failure.invalidMessage }
        try self.init(
            revision: c.decode(Int64.self, forKey: .revision), jpeg: c.decodeIfPresent(Data.self, forKey: .jpeg))
    }
    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(revision, forKey: .revision)
        if let jpeg { try c.encode(jpeg, forKey: .jpeg) } else { try c.encodeNil(forKey: .jpeg) }
    }
}
