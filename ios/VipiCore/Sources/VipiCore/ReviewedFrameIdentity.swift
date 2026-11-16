import Foundation

/// Stable semantic identity supplied only after the caller verifies a reviewed
/// frame. Pack and context identities remain evidence, not familiarity keys.
public struct ReviewedFrameIdentity: Sendable, Equatable {
    public let sourceLanguage: String, targetLanguage: String, patternID: String
    public let sourceFace: String, targetFace: String, meaning: String, reading: String
    public init?(verifiedReviewedPattern: Bool, sourceLanguage: String, targetLanguage: String,
                 patternID: String, sourceFace: String, targetFace: String, meaning: String, reading: String) {
        guard verifiedReviewedPattern,
              [sourceLanguage,targetLanguage,patternID,sourceFace,targetFace,meaning].allSatisfy({ !$0.isEmpty && $0.utf8.count <= 16_384 }),
              reading.utf8.count <= 16_384 else { return nil }
        self.sourceLanguage=sourceLanguage;self.targetLanguage=targetLanguage;self.patternID=patternID
        self.sourceFace=sourceFace;self.targetFace=targetFace;self.meaning=meaning;self.reading=reading
    }
    /// Eight exact UTF-8 fields, each prefixed with unsigned 32-bit big-endian
    /// byte length; do not normalize. HMAC with the account-local vault key.
    public var encoded: Data {
        var result=Data()
        for field in ["v2-frame-sense-1",sourceLanguage,targetLanguage,patternID,sourceFace,targetFace,meaning,reading] {
            let bytes=Data(field.utf8);var length=UInt32(bytes.count).bigEndian
            withUnsafeBytes(of:&length) { result.append(contentsOf:$0) };result.append(bytes)
        }
        return result
    }
    public static func == (lhs: Self, rhs: Self) -> Bool { lhs.encoded == rhs.encoded }
}
