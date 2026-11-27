import Foundation

/// All coordinates refer to the exact original source, never normalized or
/// translated text. These records carry a producer's evidence, not new meanings.
public struct SourceApprovedOutput: Sendable, Equatable {
    public let outputID: String
    public let range: NSRange
    public init(outputID: String, range: NSRange) {
        self.outputID = outputID
        self.range = range
    }
}
public enum SourceAtomicMode: Sendable { case none, atomic, headBackoff, ambiguous }
public struct SourceRecognition: Sendable {
    public let ruleID: String, recordSHA256: String
    public let context: NSRange, mask: NSRange?
    public let mode: SourceAtomicMode
    public let approvedOutputs: [SourceApprovedOutput]
    public init(
        ruleID: String, recordSHA256: String, context: NSRange, mask: NSRange?,
        mode: SourceAtomicMode, approvedOutputs: [SourceApprovedOutput]
    ) {
        self.ruleID = ruleID
        self.recordSHA256 = recordSHA256
        self.context = context
        self.mask = mask
        self.mode = mode
        self.approvedOutputs = approvedOutputs
    }
}

/// Nonnullable evidence from an optional catalog. Known concepts, density and
/// unavailable target faces may remove every partial unit without removing masks.
/// Catalog producers must preserve unresolved conflicts as ambiguous recognition.
public struct SourceLookupEvidence: Sendable {
    public let original: String, source: String, target: String, catalogIdentity: String
    public let partial: PartialImmersionResult?
    public let recognitions: [SourceRecognition]
    /// Optional request-bound, pre-packing reviewed pool. Legacy producers omit it.
    public let eligiblePool: [SourceReferenceUnit]?
    public let nativeSourceTokenCount: Int?
    public init(
        original: String, source: String, target: String, catalogIdentity: String,
        partial: PartialImmersionResult?, recognitions: [SourceRecognition],
        eligiblePool: [SourceReferenceUnit]? = nil, nativeSourceTokenCount: Int? = nil
    ) {
        self.original = original
        self.source = source
        self.target = target
        self.catalogIdentity = catalogIdentity
        self.partial = partial
        self.recognitions = recognitions
        self.eligiblePool = eligiblePool
        self.nativeSourceTokenCount = nativeSourceTokenCount
    }
    public func validated(
        text: String, sourceLanguage: String, targetLanguage: String,
        identity: String
    ) -> SourceLookupConstraints? {
        guard original.utf8.elementsEqual(text.utf8), source == sourceLanguage, target == targetLanguage,
            source != target, !source.isEmpty, !target.isEmpty,
            catalogIdentity == identity,
            catalogIdentity.range(of: #"^[A-Za-z0-9._:-]{1,160}$"#, options: .regularExpression) != nil,
            !original.isEmpty, original.utf16.count <= 16_384, recognitions.count <= 4096
        else { return nil }
        let edges = Set(original.indices.map { $0.utf16Offset(in: original) } + [original.utf16.count])
        func valid(_ range: NSRange) -> Bool {
            range.location >= 0 && range.location <= original.utf16.count && range.length > 0
                && range.length <= original.utf16.count - range.location && edges.contains(range.location)
                && edges.contains(NSMaxRange(range))
        }
        func contains(_ outer: NSRange, _ inner: NSRange) -> Bool {
            inner.location >= outer.location && NSMaxRange(inner) <= NSMaxRange(outer)
        }
        var approvals = 0
        for recognition in recognitions {
            guard !recognition.ruleID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                recognition.ruleID.utf16.count <= 160,
                recognition.recordSHA256.range(of: #"^[a-f0-9]{64}$"#, options: .regularExpression) != nil,
                valid(recognition.context), (recognition.mode == .none) == (recognition.mask == nil),
                recognition.approvedOutputs.count <= 4096 - approvals
            else { return nil }
            approvals += recognition.approvedOutputs.count
            if let mask = recognition.mask {
                guard valid(mask), contains(recognition.context, mask) else { return nil }
            }
            if recognition.mode == .ambiguous && !recognition.approvedOutputs.isEmpty { return nil }
            for output in recognition.approvedOutputs {
                guard !output.outputID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                    output.outputID.utf16.count <= 160, valid(output.range),
                    contains(recognition.context, output.range)
                else { return nil }
                if let mask = recognition.mask {
                    if recognition.mode == .atomic && output.range != mask { return nil }
                    if recognition.mode == .headBackoff && !contains(mask, output.range) { return nil }
                }
            }
        }
        if let partial {
            guard partial.original.utf8.elementsEqual(text.utf8),
                SourceReferencePresentation.validPartial(partial, target: target)
            else { return nil }
        }
        let constraints = SourceLookupConstraints(evidence: self)
        guard (eligiblePool == nil) == (nativeSourceTokenCount == nil) else { return nil }
        if let pool = eligiblePool, let count = nativeSourceTokenCount {
            guard pool.count <= 4096, (1...16_384).contains(count) else { return nil }
            for unit in pool {
                guard constraints.permits(range: unit.range, outputID: unit.outputID),
                    SourceReferencePresentation.create(
                        original: original, target: target, units: [unit], density: 1, nativeSourceTokenCount: count)
                        != nil
                else { return nil }
                guard unit.reviewedFrameIdentity == nil || unit.reviewedStarterIdentity == nil else { return nil }
                if let starter = unit.reviewedStarterIdentity {
                    guard starter.sourceLanguage == source, starter.targetLanguage == target,
                        starter.targetFace.utf8.elementsEqual(unit.translated.utf8),
                        starter.reading.utf8.elementsEqual((unit.reading ?? "").utf8),
                        unit.referenceID.hasSuffix(":" + starter.entryID),
                        unit.conceptID == starter.conceptID
                    else { return nil }
                }
                if let frame = unit.reviewedFrameIdentity {
                    guard frame.sourceLanguage == source, frame.targetLanguage == target,
                        frame.sourceFace.utf8.elementsEqual(unit.original.utf8),
                        frame.targetFace.utf8.elementsEqual(unit.translated.utf8),
                        frame.reading.utf8.elementsEqual((unit.reading ?? "").utf8),
                        unit.referenceID == "frame:" + unit.catalogSHA256 + ":" + frame.patternID
                    else { return nil }
                }
            }
        }
        return constraints
    }
}

/// Constructed only after complete request-bound validation. This value belongs
/// to one original-forward resolution; reverse translations never inherit it.
public struct SourceLookupConstraints: Sendable {
    public let original: String, source: String, target: String, catalogIdentity: String
    public let recognitions: [SourceRecognition]
    fileprivate init(evidence: SourceLookupEvidence) {
        original = evidence.original
        source = evidence.source
        target = evidence.target
        catalogIdentity = evidence.catalogIdentity
        recognitions = evidence.recognitions
    }
    public func matches(original: String, target: String?) -> Bool {
        self.original.utf8.elementsEqual(original.utf8) && (target == nil || self.target == target)
    }
    public func permits(range: NSRange, outputID: String? = nil) -> Bool {
        recognitions.allSatisfy { recognition in
            guard let mask = recognition.mask, NSIntersectionRange(mask, range).length > 0 else { return true }
            return recognition.mode != .ambiguous && outputID != nil
                && recognition.approvedOutputs.contains {
                    $0.outputID == outputID && $0.range == range
                }
        }
    }
    /// Alignment has no approved source output IDs, even for identical text.
    public func filterLegacy(_ value: ImmersionResult) -> ImmersionResult {
        guard matches(original: value.original, target: nil) else {
            return .init(original: value.original, translation: value.translation, spans: [])
        }
        return .init(
            original: value.original, translation: value.translation,
            spans: value.spans.filter { permits(range: $0.range) })
    }
    /// Preserve the producer's budget/order and reference-local target ranges.
    /// An empty selection remains nil; recognition is retained independently.
    public func filterPartial(_ value: PartialImmersionResult) -> PartialImmersionResult? {
        guard matches(original: value.original, target: value.targetLanguage),
            SourceReferencePresentation.validPartial(value, target: target)
        else { return nil }
        let kept = zip(value.spans, value.references).filter { permits(range: $0.0.range, outputID: $0.1.outputID) }
        guard !kept.isEmpty else { return nil }
        return .init(
            original: value.original, spans: kept.map { $0.0 }, references: kept.map { $0.1 },
            nativeSourceTokenCount: value.nativeSourceTokenCount, targetLanguage: value.targetLanguage)
    }
}
