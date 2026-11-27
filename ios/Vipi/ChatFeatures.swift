import Foundation
import ImageIO

/// Optional authenticated content shared by the app and notification extension.
struct ChatFeatures: Codable, Equatable {
    struct Reply: Codable, Equatable {
        let message_id: UUID
        let sender_id: UUID
        let kind: String
        let excerpt: String
        var valid: Bool {
            ["text", "photo", "video", "voice"].contains(kind) && !excerpt.isEmpty && excerpt.utf8.count <= 512
        }
    }
    struct Preview: Codable, Equatable {
        let url: String
        let title: String
        var thumbnail_jpeg: Data? = nil
        func validated(in text: String) -> Self? {
            guard text.contains(url), Self.urls(in: text).contains(where: { $0.absoluteString == url }),
                !title.isEmpty, !title.unicodeScalars.contains(where: CharacterSet.controlCharacters.contains),
                title.utf8.count <= 512
            else { return nil }
            var value = self
            if let data = thumbnail_jpeg, !Self.safeThumbnail(data) { value.thumbnail_jpeg = nil }
            return value
        }
        static func safeThumbnail(_ data: Data) -> Bool {
            guard data.count <= 8192, let src = CGImageSourceCreateWithData(data as CFData, nil),
                CGImageSourceGetType(src) as String? == "public.jpeg",
                CGImageSourceGetCount(src) == 1,
                let info = CGImageSourceCopyPropertiesAtIndex(src, 0, nil) as? [CFString: Any],
                let w = info[kCGImagePropertyPixelWidth] as? Int, let h = info[kCGImagePropertyPixelHeight] as? Int
            else { return false }
            return (1...512).contains(w) && (1...512).contains(h)
        }
        static func publicURL(_ url: URL) -> Bool {
            guard url.absoluteString.utf8.count <= 2048, url.scheme?.lowercased() == "https",
                url.user == nil, url.password == nil, url.port == nil || url.port == 443,
                let host = url.host?.lowercased(), host.contains("."), !host.hasSuffix("."),
                ![".localhost", ".local", ".internal", ".home", ".lan", ".test", ".onion", ".arpa"].contains(
                    where: host.hasSuffix),
                host.split(separator: ".").last?.contains(where: { $0.isLetter }) == true,
                host.utf8.allSatisfy({ ($0 >= 97 && $0 <= 122) || ($0 >= 48 && $0 <= 57) || $0 == 45 || $0 == 46 })
            else { return false }
            return true
        }
        private static let detector = try? NSDataDetector(types: NSTextCheckingResult.CheckingType.link.rawValue)
        static func firstURL(in text: String) -> URL? { urls(in: text).first }
        private static func urls(in text: String) -> [URL] {
            guard text.utf8.count <= 32768 else { return [] }
            var result = [URL]()
            for match in detector?.matches(in: text, range: NSRange(text.startIndex..., in: text)) ?? [] {
                guard let range = Range(match.range, in: text), let url = URL(string: String(text[range])),
                    publicURL(url)
                else { continue }
                result.append(url)
            }
            return result
        }
    }
    struct Reaction: Codable, Equatable {
        let message_id: UUID
        let target_sender_id: UUID
        let sequence: Int64
        let emoji: String?
        enum CodingKeys: String, CodingKey { case message_id, target_sender_id, sequence, emoji }
        init(message_id: UUID, target_sender_id: UUID, sequence: Int64, emoji: String?) {
            self.message_id = message_id
            self.target_sender_id = target_sender_id
            self.sequence = sequence
            self.emoji = emoji
        }
        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            self.init(
                message_id: try c.decode(UUID.self, forKey: .message_id),
                target_sender_id: try c.decode(UUID.self, forKey: .target_sender_id),
                sequence: try c.decode(Int64.self, forKey: .sequence),
                emoji: try c.decode(String?.self, forKey: .emoji))
        }
        func encode(to encoder: Encoder) throws {
            var c = encoder.container(keyedBy: CodingKeys.self)
            try c.encode(message_id, forKey: .message_id)
            try c.encode(target_sender_id, forKey: .target_sender_id)
            try c.encode(sequence, forKey: .sequence)
            try c.encode(emoji, forKey: .emoji)
        }
        var valid: Bool {
            guard sequence > 0, sequence <= Int64(Int32.max) else { return false }
            guard let emoji else { return true }
            return emoji.count == 1 && emoji.utf8.count <= 64
                && emoji.unicodeScalars.contains { $0.value == 0x20e3 || ($0.properties.isEmoji && $0.value > 127) }
        }
    }
    var version = 1
    var reply: Reply? = nil
    var link_preview: Preview? = nil
    var reaction: Reaction? = nil
    func validated(in text: String) -> Self? {
        guard version == 1 else { return nil }
        if let reaction {
            return text == "Reaction" && reaction.valid && reply == nil && link_preview == nil ? self : nil
        }
        let validReply = reply.flatMap { $0.valid ? $0 : nil }
        let preview = link_preview?.validated(in: text)
        return validReply != nil || preview != nil ? Self(reply: validReply, link_preview: preview) : nil
    }
    static func fit(_ features: ChatFeatures?, encode: (ChatFeatures?) throws -> Data) throws -> (ChatFeatures?, Data) {
        var value = features
        var bytes = try encode(value)
        if bytes.count > 60 * 1024, value?.link_preview?.thumbnail_jpeg != nil {
            value?.link_preview?.thumbnail_jpeg = nil
            bytes = try encode(value)
        }
        if bytes.count > 60 * 1024, value?.link_preview != nil {
            value?.link_preview = nil
            if value?.reply == nil { value = nil }
            bytes = try encode(value)
        }
        return (value, bytes)
    }
    static func excerpt(_ value: String) -> String {
        var result = "", bytes = 0
        for c in value {
            let count = String(c).utf8.count
            guard bytes + count <= 512 else { break }
            bytes += count
            result.append(c)
        }
        return result
    }
}
/// Decode independently, preserving message text if an optional field is malformed.
struct WireChatFeatures: Codable {
    let value: ChatFeatures?
    init(_ features: ChatFeatures) { value = features }
    init(from decoder: Decoder) throws { value = try? ChatFeatures(from: decoder) }
    func encode(to encoder: Encoder) throws { try value?.encode(to: encoder) }
}

extension ChatFeatures {
    private enum Fields: String, CodingKey { case version, reply, link_preview, reaction }
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: Fields.self)
        version = try c.decode(Int.self, forKey: .version)
        if c.contains(.reaction) {
            guard c.allKeys.count == 2 else {
                throw DecodingError.dataCorruptedError(
                    forKey: .reaction, in: c, debugDescription: "Mixed reaction payload")
            }
            reaction = try c.decode(Reaction.self, forKey: .reaction)
        } else {
            reply = try? c.decode(Reply.self, forKey: .reply)
            link_preview = try? c.decode(Preview.self, forKey: .link_preview)
        }
    }
}
extension ChatFeatures.Preview {
    private enum Fields: String, CodingKey { case url, title, thumbnail_jpeg }
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: Fields.self)
        url = try c.decode(String.self, forKey: .url)
        title = try c.decode(String.self, forKey: .title)
        thumbnail_jpeg = try? c.decode(Data.self, forKey: .thumbnail_jpeg)
    }
}
