import Foundation

/// Stable displayed-form identity minted only from a verified reviewed starter
/// entry after its current occurrence passes all source guards. This records a
/// displayed form, not a sense, mastery, or permission to bypass future guards.
public struct ReviewedStarterIdentity: Sendable, Equatable {
    public let sourceLanguage:String, targetLanguage:String, entryID:String, conceptID:String
    public let partOfSpeech:String, guardValue:String, canonicalSource:String, targetFace:String, reading:String
    public init?(verifiedReviewedEntry:Bool,sourceLanguage:String,targetLanguage:String,entryID:String,conceptID:String,
                 partOfSpeech:String,guardValue:String,canonicalSource:String,targetFace:String,reading:String) {
        guard verifiedReviewedEntry,
              [sourceLanguage,targetLanguage,entryID,conceptID,partOfSpeech,canonicalSource,targetFace].allSatisfy({ !$0.isEmpty && $0.utf8.count <= 16_384 }),
              guardValue.utf8.count <= 16_384, reading.utf8.count <= 16_384 else { return nil }
        self.sourceLanguage=sourceLanguage;self.targetLanguage=targetLanguage;self.entryID=entryID;self.conceptID=conceptID
        self.partOfSpeech=partOfSpeech;self.guardValue=guardValue;self.canonicalSource=canonicalSource;self.targetFace=targetFace;self.reading=reading
    }
    public var encoded:Data {
        var result=Data()
        for field in ["v2-starter-display-1",sourceLanguage,targetLanguage,entryID,conceptID,partOfSpeech,guardValue,canonicalSource,targetFace,reading] {
            let bytes=Data(field.utf8);var length=UInt32(bytes.count).bigEndian
            withUnsafeBytes(of:&length) { result.append(contentsOf:$0) };result.append(bytes)
        }
        return result
    }
    public static func == (lhs:Self,rhs:Self)->Bool { lhs.encoded == rhs.encoded }
}
