import Foundation
import CryptoKit
import VipiCore

/// Versioned source-only beginner pack. Reviewed starter; the withheld winter entry is absent.
@MainActor final class JapaneseStarterLookup {
    static let promotionEnabled = true
    static let packingEnabled = true // Qualified native packing; see starter-packing-density-r01.
    static func whitespaceGap(_ value: String) -> Bool {
        !value.isEmpty && value.unicodeScalars.allSatisfy { CharacterSet.whitespacesAndNewlines.contains($0) }
    }
    struct Entry: Decodable {
        let id, source, target, category, pos, reading, reading_kana, concept_id, record_sha256: String
        let train_rank: Int
        let source_tokens: [String]
        let guardValue: String?
        let following: [String]?
        enum CodingKeys: String, CodingKey {
            case id, source, target, category, pos, reading, reading_kana, concept_id, record_sha256, train_rank, source_tokens, following
            case guardValue = "guard"
        }
    }
    struct Pack: Decodable {
        struct Context: Decodable { let determiners, prepositions, object_verbs, copulas: [String] }
        let schema, version, source, target: String
        let entries: [Entry]
        let source_context_sets: Context
    }
    struct Manifest: Decodable { let schema, file, sha256, version: String; let bytes, entries: Int }
    enum Invalid: Error { case pack, input }
    let pack: Pack
    let sha: String
    private let packMultiple: Bool
    private var packIdentity: String { pack.version + ":" + sha }
    var identity: String { packIdentity + (packMultiple ? ":packing-1" : "") }
    var trace: [[String: Any]] = []
    private let words = try! NSRegularExpression(pattern: #"[\p{L}\p{Nl}\p{No}]+(?:['’][\p{L}\p{Nl}\p{No}]+)*"#)
    private let literals = try! NSRegularExpression(pattern: #"https?://\S+|\b[^\s@]+@[^\s@]+\.[^\s@]+|```[\s\S]*?```|`[^`]*`"#)
    static func digest(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
    private func fold(_ s: String) -> String { s.folding(options: [.caseInsensitive], locale: Locale(identifier: "en_US_POSIX")).replacingOccurrences(of: "’", with: "'") }
    init(data: Data, manifest: Data, packMultiple: Bool = false) throws {
        self.packMultiple = packMultiple
        let m = try JSONDecoder().decode(Manifest.self, from: manifest)
        guard m.schema == "vipi-source-starter-manifest-1", m.file.range(of: "^starter-en-ja-[0-9]{3}\\.json$", options: .regularExpression) != nil,
              m.bytes == data.count, data.count <= 1_048_576, Self.digest(data) == m.sha256 else { throw Invalid.pack }
        let p = try JSONDecoder().decode(Pack.self, from: data)
        guard p.schema == "vipi-source-starter-1", p.source == "en", p.target == "ja", p.version == m.version,
              p.entries.count == m.entries, (1...512).contains(p.entries.count), Set(p.entries.map(\.id)).count == p.entries.count,
              p.entries.allSatisfy({ !$0.id.isEmpty && !$0.source_tokens.isEmpty && !$0.target.isEmpty && !$0.reading.isEmpty && !$0.reading_kana.isEmpty && !$0.concept_id.isEmpty &&
                  [nil,"ordinary_noun_context","interrogative"].contains($0.guardValue) && ["content","function"].contains($0.category) &&
                  $0.record_sha256.range(of: "^[a-f0-9]{64}$", options: .regularExpression) != nil }) else { throw Invalid.pack }
        pack = p; sha = m.sha256
    }
    static func bundledIfPromoted() -> SourceUnitLookup? {
        guard promotionEnabled, let root = Bundle.main.resourceURL?.appendingPathComponent("immersion"),
              let manifest = try? Data(contentsOf: root.appendingPathComponent("starter-catalog.json")),
              let metadata = try? JSONDecoder().decode(Manifest.self, from: manifest),
              metadata.file.range(of: "^starter-en-ja-[0-9]{3}\\.json$", options: .regularExpression) != nil,
              let data = try? Data(contentsOf: root.appendingPathComponent(metadata.file)),
              let owner = try? JapaneseStarterLookup(data: data, manifest: manifest, packMultiple: packingEnabled) else { return nil }
        return owner.provider()
    }
    func provider() -> SourceUnitLookup {
        SourceUnitLookup(identity: identity) { context in try self.resolve(context) }
    }
    func resolve(_ context: SourceUnitLookup.Context, protectedRanges: [NSRange] = [], sourceMasks: [NSRange] = []) throws -> SourceLookupEvidence {
        trace = []
        let original = context.original, pair = context.pair, density = context.density
        func evidence(_ partial: PartialImmersionResult?, _ recognition: [SourceRecognition]) -> SourceLookupEvidence {
            .init(original: original, source: pair.source, target: pair.target, catalogIdentity: identity, partial: partial, recognitions: recognition)
        }
        guard pair.source == "en", pair.target == "ja" else { return evidence(nil, []) }
        guard !original.isEmpty, original.utf16.count <= 16_384, density.isFinite, density >= 0, density <= 1 else { throw Invalid.input }
        let text = original as NSString
        let native = LocalImmersion.words(original, language: "en")
        guard let basis = NativeSourceTokenBasis(original: original, wordRanges: native) else { throw Invalid.input }
        let budget = density > 0 ? max(1, Int(Double(basis.count) * density)) : 0
        let tokens = words.matches(in: original, range: NSRange(location: 0, length: text.length)).map(\.range)
        let keys = tokens.map { fold(text.substring(with: $0)) }
        let protection = protectedRanges + sourceMasks + literals.matches(in: original, range: NSRange(location: 0, length: text.length)).map(\.range)
        let lefts = Set(pack.source_context_sets.determiners + pack.source_context_sets.prepositions + pack.source_context_sets.object_verbs)
        struct Hit { let entry: Entry, range: NSRange, cost: Int, outputID: String, reason: String? }
        var hits: [Hit] = []
        func gap(_ a: Int, _ b: Int) -> String { text.substring(with: NSRange(location: a, length: b-a)) }
        for i in tokens.indices {
            for entry in pack.entries {
                let j = i + entry.source_tokens.count
                guard j <= keys.count, Array(keys[i..<j]) == entry.source_tokens else { continue }
                let unit = NSRange(location: tokens[i].location, length: NSMaxRange(tokens[j-1])-tokens[i].location)
                let source = text.substring(with: unit), first = text.substring(with: tokens[i])
                var prefix = text.substring(to: unit.location).trimmingCharacters(in: .whitespacesAndNewlines)
                while let last = prefix.last, "\"'“”‘’".contains(last) { prefix.removeLast() }
                let initial = prefix.isEmpty || ".!?".contains(prefix.last!)
                let touched = native.filter { NSIntersectionRange($0, unit).length > 0 }
                let cost = basis.cost(for: unit)
                var reason: String?
                if protection.contains(where: { NSIntersectionRange($0, unit).length > 0 }) { reason = "protected_source" }
                else if (i..<(j-1)).contains(where: { !Self.whitespaceGap(gap(NSMaxRange(tokens[$0]), tokens[$0+1].location)) }) { reason = "noncontiguous_source_unit" }
                else if keys[i] != "i", first.count > 1, first == first.uppercased(), first != first.lowercased() { reason = "uppercase_identifier" }
                else if keys[i] != "i", first.first?.isUppercase == true, !initial { reason = "mid_sentence_capital" }
                else if entry.guardValue == "interrogative" {
                    if !initial { reason = "question_not_sentence_initial" }
                    else if j >= keys.count || !(entry.following ?? []).contains(keys[j]) { reason = "question_right_context_absent" }
                    else if (i..<j).contains(where: { !gap(NSMaxRange(tokens[$0]), tokens[$0+1].location).trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }) { reason = "noncontiguous_question_context" }
                } else if entry.guardValue == "ordinary_noun_context" {
                    let left = i > 0 && gap(NSMaxRange(tokens[i-1]), unit.location).trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? keys[i-1] : ""
                    let right = j < keys.count ? keys[j] : ""
                    if !lefts.contains(left) && !(initial && pack.source_context_sets.copulas.contains(right)) { reason = "noun_context_absent" }
                }
                if reason == nil && (cost == nil || touched.first?.location != unit.location || touched.last.map(NSMaxRange) != NSMaxRange(unit)) { reason = "partial_native_word" }
                if reason == nil && fold(source.precomposedStringWithCompatibilityMapping) == fold(entry.target.precomposedStringWithCompatibilityMapping) { reason = "unchanged_normalized_face" }
                if reason == nil && !TranslationIntegrity.preservesIdentifiers(original: original, translation: text.replacingCharacters(in: unit, with: entry.target)) { reason = "full_message_literal_integrity" }
                if reason == nil && context.knownConceptIDs.contains(entry.concept_id) { reason = "caller_known_concept" }
                if reason == nil && (cost ?? Int.max) > budget { reason = "native_density_budget" }
                let outputID = entry.id + "@\(unit.location):\(NSMaxRange(unit))"
                hits.append(.init(entry: entry, range: unit, cost: cost ?? 0, outputID: outputID, reason: reason))
                trace.append(["entry_id":entry.id,"concept_id":entry.concept_id,"source":source,"target":entry.target,"reading":entry.reading,"source_utf16":[unit.location,NSMaxRange(unit)],"reason":reason as Any? ?? NSNull(),"record_sha256":entry.record_sha256])
                guard hits.count <= 4096 else { throw Invalid.input }
            }
        }
        let found = hits.filter { $0.reason == nil }.sorted {
            if ($0.entry.category == "content") != ($1.entry.category == "content") { return $0.entry.category == "content" }
            if $0.entry.train_rank != $1.entry.train_rank { return $0.entry.train_rank < $1.entry.train_rank }
            if $0.entry.source_tokens.count != $1.entry.source_tokens.count { return $0.entry.source_tokens.count > $1.entry.source_tokens.count }
            return $0.range.location < $1.range.location
        }
        var chosen: [Hit] = []; var used = 0
        for hit in found {
            // The existing presentation contract accepts at most 128 whole units.
            if chosen.count >= (packMultiple ? 128 : 1) { break }
            if used + hit.cost > budget || chosen.contains(where: { NSIntersectionRange($0.range,hit.range).length > 0 }) { continue }
            chosen.append(hit); used += hit.cost
        }
        let units = chosen.sorted { $0.range.location < $1.range.location }.map { h in SourceReferenceUnit(range:h.range,original:text.substring(with:h.range),translated:h.entry.target,reading:h.entry.reading,referenceID:packIdentity+":"+h.entry.id,catalogSHA256:sha,nativeSourceTokens:h.cost,conceptID:h.entry.concept_id,outputID:h.outputID) }
        let partial = SourceReferencePresentation.create(original:original,target:"ja",units:units,density:density,nativeSourceTokenCount:basis.count)
        // Merge overlapping matches so short/long valid alternatives do not
        // veto each other. Recognition survives known/budget/guard abstention.
        var groups: [[Hit]] = []
        for h in hits.sorted(by: { ($0.range.location,$0.range.length) < ($1.range.location,$1.range.length) }) {
            if let last = groups.last, h.range.location < last.map({ NSMaxRange($0.range) }).max()! { groups[groups.count-1].append(h) }
            else { groups.append([h]) }
        }
        var recognition = groups.enumerated().map { n,g -> SourceRecognition in
            let start = g.map(\.range.location).min()!, end = g.map { NSMaxRange($0.range) }.max()!
            let range = NSRange(location:start,length:end-start)
            return .init(ruleID:"starter-\(n)",recordSHA256:Self.digest(Data(g.map(\.entry.record_sha256).sorted().joined().utf8)),context:range,mask:range,mode:.headBackoff,approvedOutputs:g.filter{$0.reason == nil}.map{.init(outputID:$0.outputID,range:$0.range)})
        }
        recognition += protection.enumerated().map { n,r in .init(ruleID:"protection-\(n)",recordSHA256:sha,context:r,mask:r,mode:.ambiguous,approvedOutputs:[]) }
        let result = evidence(partial, recognition)
        guard result.validated(text:original,sourceLanguage:"en",targetLanguage:"ja",identity:identity) != nil else { throw Invalid.input }
        return result
    }
}
