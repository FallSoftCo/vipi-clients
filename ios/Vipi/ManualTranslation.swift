import Foundation
import CryptoKit
import VipiCore

/// Immutable original-source coordinates; displayed attachment text is never input.
struct ManualTranslationRequest: Sendable, Equatable {
    let messageID: String, originalText: String
    let startUTF16: Int, endUTF16: Int
    let knownLanguage: String, learningLanguage: String, inputLanguage: String?
    let generation: UInt64
    let ownerGeneration: UUID
    let selectionIdentity: String
    init(messageID: String, originalText: String, startUTF16: Int, endUTF16: Int,
         knownLanguage: String, learningLanguage: String, inputLanguage: String?, generation: UInt64, ownerGeneration: UUID) {
        self.messageID = messageID; self.originalText = originalText; self.startUTF16 = startUTF16; self.endUTF16 = endUTF16
        self.knownLanguage = knownLanguage; self.learningLanguage = learningLanguage; self.inputLanguage = inputLanguage
        self.generation = generation; self.ownerGeneration = ownerGeneration
        let values = [messageID, originalText, String(startUTF16), String(endUTF16), knownLanguage, learningLanguage,
                      inputLanguage ?? "", String(generation), ownerGeneration.uuidString]
        let bytes = Data(values.map { "\($0.utf8.count):" + $0 }.joined().utf8)
        selectionIdentity = SHA256.hash(data: bytes).map { String(format:"%02x",$0) }.joined()
    }
    static func == (lhs: Self, rhs: Self) -> Bool { lhs.selectionIdentity == rhs.selectionIdentity }
}
/// Never projects normalized display offsets onto a different raw message.
struct ManualSourceRange: Sendable, Equatable {
    let startUTF16:Int, endUTF16:Int, expanded:Bool
}
enum ManualSourceCoordinates {
    static func resolve(rawOriginal:String,displayedSource:String,startUTF16:Int,endUTF16:Int)->ManualSourceRange? {
        guard !rawOriginal.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty,rawOriginal.utf8.count<=32_768 else{return nil}
        func whole()->ManualSourceRange{.init(startUTF16:0,endUTF16:rawOriginal.utf16.count,expanded:true)}
        guard startUTF16>=0,endUTF16>startUTF16,endUTF16<=displayedSource.utf16.count else{return whole()}
        var boundaries:Set<Int>=[0],offset=0
        for character in displayedSource{offset+=String(character).utf16.count;boundaries.insert(offset)}
        guard boundaries.contains(startUTF16),boundaries.contains(endUTF16),
              rawOriginal.utf8.elementsEqual(displayedSource.utf8) else{return whole()}
        return .init(startUTF16:startUTF16,endUTF16:endUTF16,expanded:false)
    }
}
struct ManualTranslationResult: Sendable {
    let request: ManualTranslationRequest, originalSlice: String, targetText: String
    let reading: FullReading?
    let sourceLanguage: String, targetLanguage: String
    let sourceContextText:String, sourceContextStartUTF16:Int, sourceContextEndUTF16:Int
    let contextExpanded:Bool
    let sourceReading:FullReading?
}
enum ManualTranslationStatus: String, Sendable { case ready, invalidInput, invalidLanguage, modelNotReady, invalidResult, stale, timeout, error }
struct ManualTranslationOutcome: Sendable {
    let status: ManualTranslationStatus, result: ManualTranslationResult?
    init(_ status: ManualTranslationStatus, result: ManualTranslationResult? = nil) { self.status = status; self.result = result }
}
enum ManualTranslationFailure: Error { case timeout }

/// Local translation and display reading only; no alignment or learning-state writes.
enum ManualTranslationResolver {
    private static let supported: Set<String> = ["en","es","fr","de","it","pt","ar","zh","ja","ko","sw"]
    private static let latin = supported.subtracting(["ar","zh","ja","ko"])
    private static func scriptLanguage(_ text: String, pair: [String]) -> String? {
        let masked = NSMutableString(string:text)
        for range in TranslationIntegrity.protectedLiteralRanges(text).reversed() { masked.replaceCharacters(in:range,with:" ") }
        let letters = (masked as String).unicodeScalars.filter { CharacterSet.letters.contains($0) && $0.value != 0x30FC }
        guard !letters.isEmpty else { return nil }
        let input = String(String.UnicodeScalarView(letters))
        let categories: [(String, Set<String>)] = [
            (#"\p{Latin}"#, latin), (#"\p{Han}"#, ["zh","ja"]),
            (#"[\p{Hiragana}\p{Katakana}]"#, ["ja"]), (#"\p{Hangul}"#, ["ko"]), (#"\p{Arabic}"#, ["ar"])
        ]
        guard input.range(of:#"[^\p{Latin}\p{Han}\p{Hiragana}\p{Katakana}\p{Hangul}\p{Arabic}]"#,options:.regularExpression) == nil else { return nil }
        let present = categories.filter { input.range(of:$0.0,options:.regularExpression) != nil }
        let candidates = pair.filter { language in present.allSatisfy { $0.1.contains(language) } }
        return candidates.count == 1 ? candidates[0] : nil
    }
    static func slice(_ request: ManualTranslationRequest) -> String? {
        let text = request.originalText
        guard !request.messageID.isEmpty, !text.isEmpty, text.utf8.count <= 32_768, request.startUTF16 >= 0,
              request.endUTF16 > request.startUTF16, request.endUTF16 <= text.utf16.count else { return nil }
        var boundaries: Set<Int> = [0], offset = 0
        for character in text { offset += String(character).utf16.count; boundaries.insert(offset) }
        guard boundaries.contains(request.startUTF16), boundaries.contains(request.endUTF16) else { return nil }
        let value = (text as NSString).substring(with:NSRange(location:request.startUTF16,length:request.endUTF16-request.startUTF16))
        return value.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty ? nil : value
    }
    private struct Chunk { let text: String, literal: Bool }
    private static func chunks(_ text:String) -> [Chunk] {
        let native = text as NSString, protected = TranslationIntegrity.protectedLiteralRanges(text)
        var boundaries:[Int] = [0], offset=0
        for character in text { offset += String(character).utf16.count; boundaries.append(offset) }
        var cursor=0, result:[Chunk]=[]
        while cursor < native.length {
            if let literal = protected.first(where: { $0.location == cursor && $0.length > 8192 }) {
                result.append(.init(text:native.substring(with:literal),literal:true));cursor=NSMaxRange(literal);continue
            }
            var end=min(native.length,cursor+8192)
            if let literal=protected.first(where: { end > $0.location && end < NSMaxRange($0) }) { end=literal.location }
            end=boundaries.last(where:{$0<=end}) ?? cursor
            guard end>cursor else{return []}
            if end<native.length, let natural=boundaries.last(where:{ i in
                i>cursor+(end-cursor)/2 && i<end && i<native.length &&
                (Unicode.Scalar(native.character(at:i)).map { CharacterSet.whitespacesAndNewlines.contains($0) } == true) &&
                !protected.contains(where:{NSLocationInRange(i,$0)})
            }) { end=natural }
            let value=native.substring(with:NSRange(location:cursor,length:end-cursor))
            let core=value.trimmingCharacters(in:.whitespacesAndNewlines)
            if core.isEmpty {result.append(.init(text:value,literal:true))}
            else {
                let first=value.prefix(while:{$0.isWhitespace}).utf16.count
                let tail=value.reversed().prefix(while:{$0.isWhitespace}).reversed().map(String.init).joined().utf16.count
                let ns=value as NSString
                if first>0 {result.append(.init(text:ns.substring(to:first),literal:true))}
                result.append(.init(text:ns.substring(with:NSRange(location:first,length:ns.length-first-tail)),literal:false))
                if tail>0 {result.append(.init(text:ns.substring(from:ns.length-tail),literal:true))}
            }
            cursor=end
        }
        return result
    }
    static func sourceContext(_ request:ManualTranslationRequest)->ManualSourceContext? {
        guard slice(request) != nil else{return nil}
        return ManualTranslationContext.enclosing(request.originalText,start:request.startUTF16,end:request.endUTF16,
            language:request.inputLanguage ?? request.knownLanguage)
    }
    private static func detectionContext(_ source:ManualSourceContext,request:ManualTranslationRequest)->String {
        guard source.text.utf16.count>16_384 else{return source.text}
        var boundaries:[Int]=[0],offset=0
        for character in source.text {offset+=String(character).utf16.count;boundaries.append(offset)}
        let start=boundaries.first(where:{$0>=max(0,request.startUTF16-source.startUTF16-4096)}) ?? 0
        let end=boundaries.last(where:{$0<=start+16_384}) ?? start
        return (source.text as NSString).substring(with:NSRange(location:start,length:end-start))
    }
    @MainActor static func resolve(_ request: ManualTranslationRequest, valid: () -> Bool,
        reference: (String,String,String) async throws -> String?, identify: (String) async throws -> String?,
        modelsReady: (String,String) async throws -> Bool, translate: (String,String,String) async throws -> String,
        reading: (String,String) async -> FullReading?, deadline:ContinuousClock.Instant? = nil) async throws -> ManualTranslationOutcome {
        func stop(_ status: ManualTranslationStatus) -> ManualTranslationOutcome { .init(valid() ? status : .stale) }
        guard valid() else { return stop(.stale) }
        guard let slice = slice(request),let context=sourceContext(request) else { return stop(.invalidInput) }
        let sourceText=context.text
        let known = request.knownLanguage, learning = request.learningLanguage, pair = [known,learning]
        guard known != learning, pair.allSatisfy(supported.contains), request.inputLanguage == nil || pair.contains(request.inputLanguage!) else { return stop(.invalidInput) }
        do {
            var source = request.inputLanguage ?? scriptLanguage(sourceText,pair:pair)
            if source == nil {
                let forward = try await reference(sourceText,known,learning)
                guard valid() else { return stop(.stale) }
                let reverse = forward == nil ? try await reference(sourceText,learning,known) : nil
                guard valid() else { return stop(.stale) }
                if forward != nil { source = known }
                else if reverse != nil { source = learning }
                else { source = try await identify(detectionContext(context,request:request)) }
                guard valid() else { return stop(.stale) }
            }
            guard valid() else { return stop(.stale) }
            guard let from = source, pair.contains(from) else { return stop(.invalidLanguage) }
            let to = from == known ? learning : known
            let authored = try await reference(sourceText,from,to)
            guard valid() else { return stop(.stale) }
            let translated: String
            if let authored { translated = authored }
            else {
                guard try await modelsReady(from,to) else { return stop(.modelNotReady) }
                guard valid() else { return stop(.stale) }
                let parts=chunks(sourceText)
                guard !parts.isEmpty else{return stop(.invalidInput)}
                var output=""
                for part in parts {
                    guard valid() else{return stop(.stale)}
                    if part.literal {output+=part.text} else {output+=try await translate(part.text,from,to)}
                }
                translated=output
            }
            guard valid() else { return stop(.stale) }
            guard !translated.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty, translated.utf16.count <= 65_536,
                  TranslationIntegrity.preservesIdentifiers(original:sourceText,translation:translated) else { return stop(.invalidResult) }
            try Task.checkCancellation()
            if let deadline,ContinuousClock.now>=deadline {throw ManualTranslationFailure.timeout}
            let guide = await reading(translated,to)
            try Task.checkCancellation()
            if let deadline,ContinuousClock.now>=deadline {throw ManualTranslationFailure.timeout}
            guard valid() else { return stop(.stale) }
            let sourceGuide:FullReading?
            if from == learning,["ar","zh","ja","ko"].contains(from) { sourceGuide = await reading(sourceText,from) }
            else { sourceGuide = nil }
            try Task.checkCancellation()
            if let deadline,ContinuousClock.now>=deadline {throw ManualTranslationFailure.timeout}
            guard valid() else { return stop(.stale) }
            return .init(.ready,result:.init(request:request,originalSlice:slice,targetText:translated,reading:guide,sourceLanguage:from,targetLanguage:to,sourceContextText:sourceText,sourceContextStartUTF16:context.startUTF16,sourceContextEndUTF16:context.endUTF16,contextExpanded:context.startUTF16 != request.startUTF16 || context.endUTF16 != request.endUTF16,sourceReading:sourceGuide))
        } catch is CancellationError { throw CancellationError() }
        catch ManualTranslationFailure.timeout { return stop(.timeout) }
        catch { return stop(.error) }
    }
}
