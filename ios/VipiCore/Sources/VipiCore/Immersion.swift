import Foundation

/// Entries contain surface forms, not context-free substitutions. A candidate
/// must also occur unambiguously in the translation of this exact message.
/// Ephemeral focus proved by an exact context match; never decoded from a pack.
public struct VocabularySourceScope: Sendable, Equatable {
    public let original: String, start: Int, end: Int
    public init(original: String, start: Int, end: Int) { self.original=original;self.start=start;self.end=end }
}
/// Ephemeral target focus proved by a matched target context, bound to the
/// actual translation. A generic dictionary cannot deserialize this scope.
public struct VocabularyTargetScope: Sendable, Equatable {
    public let translation: String, start: Int, end: Int
    public init(translation: String,start: Int,end: Int) {self.translation=translation;self.start=start;self.end=end}
}
/// Explicit lexical focus inside an attested target word, e.g. 시간 inside 시간이.
public struct VocabularyTargetForm: Sendable, Equatable {
    public let surface: String, target: String, start: Int, end: Int
    public init(surface: String,target: String,start: Int,end: Int) {self.surface=surface;self.target=target;self.start=start;self.end=end}
}

public struct VocabularyEntry: Codable, Sendable, Equatable {
    public let source: String
    public let targets: [String]
    public let romanizations: [String: [String]]
    public let contextHints: [String]
    public let requiresContext: Bool
    public let sourceScope: VocabularySourceScope?
    public let targetForms: [VocabularyTargetForm]
    public let targetScope: VocabularyTargetScope?
    public let protectInner: Bool
    public let unresolvedNativeSenses: Bool
    public init(source: String, targets: [String], romanizations: [String: [String]] = [:], contextHints: [String] = [], requiresContext: Bool = false, sourceScope: VocabularySourceScope? = nil, targetForms: [VocabularyTargetForm] = [], targetScope: VocabularyTargetScope? = nil, protectInner: Bool = false, unresolvedNativeSenses: Bool = false) {
        self.source = source; self.targets = targets; self.romanizations = romanizations; self.contextHints = contextHints
        self.requiresContext = requiresContext
        self.sourceScope = sourceScope
        self.targetForms = targetForms
        self.targetScope = targetScope
        self.protectInner = protectInner
        self.unresolvedNativeSenses = unresolvedNativeSenses
    }
    private enum CodingKeys: String, CodingKey { case source, targets, romanizations, contextHints, requiresContext }
    public init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        source = try values.decode(String.self, forKey: .source)
        targets = try values.decode([String].self, forKey: .targets)
        romanizations = try values.decodeIfPresent([String: [String]].self, forKey: .romanizations) ?? [:]
        contextHints = try values.decodeIfPresent([String].self, forKey: .contextHints) ?? []
        requiresContext = try values.decodeIfPresent(Bool.self, forKey: .requiresContext) ?? false
        sourceScope = nil
        targetForms = []
        targetScope = nil
        protectInner = false
        unresolvedNativeSenses = false
    }
}

public struct ImmersionSpan: Sendable, Equatable, Identifiable {
    public let range: NSRange
    public let original: String
    public let translated: String
    public let targetRange: NSRange
    public let romanization: String?
    public var id: Int { range.location }
    public var displayedTarget: String { romanization ?? translated }
}

public struct SpeechSpan: Sendable, Equatable {
    public let text: String
    public let language: String
    public init(text: String, language: String) { self.text = text; self.language = language }
}

public struct ImmersionResult: Sendable, Equatable {
    public let original: String
    public let translation: String
    public let spans: [ImmersionSpan]

    public func speech(source: String, target: String, revealed: Set<Int> = []) -> [SpeechSpan] {
        var result: [SpeechSpan] = []
        let ns = original as NSString
        var cursor = 0
        for span in spans {
            if span.range.location > cursor {
                result.append(.init(text: ns.substring(with: NSRange(location: cursor, length: span.range.location - cursor)), language: source))
            }
            let showOriginal = revealed.contains(span.id)
            result.append(.init(text: showOriginal ? span.original : span.translated, language: showOriginal ? source : target))
            cursor = NSMaxRange(span.range)
        }
        if cursor < ns.length { result.append(.init(text: ns.substring(from: cursor), language: source)) }
        return result
    }
}

public struct ImmersionEngine: Sendable {
    public init() {}

    public func align(original: String, translation: String, entries: [VocabularyEntry], density: Double, targetLanguage: String? = nil,
                      sourceBoundaries: Set<Int>? = nil, targetBoundaries: Set<Int>? = nil, sourceTokenCount: Int? = nil,
                      sourceUnitTokenCounts: [NSRange: Int]? = nil, supplementalEntries: [VocabularyEntry] = []) -> ImmersionResult {
        let empty = ImmersionResult(original: original, translation: translation, spans: [])
        guard !original.isEmpty, !translation.isEmpty, density.isFinite, density > 0,
              original.utf16.count <= 16_384, translation.utf16.count <= 32_768 else { return empty }
        if !supplementalEntries.isEmpty {
            // Retain all primary claims/guards. Supplemental evidence may fill
            // gaps but cannot take an accepted source or target focus away.
            let primary = align(original: original, translation: translation, entries: entries, density: 1,
                targetLanguage: targetLanguage, sourceBoundaries: sourceBoundaries,
                targetBoundaries: targetBoundaries, sourceTokenCount: sourceTokenCount, sourceUnitTokenCounts: sourceUnitTokenCounts)
            let additions = supplementalEntries.filter { entry in
                guard let source = entry.sourceScope, let target = entry.targetScope,
                      source.original == original, target.translation == translation,
                      source.start >= 0, source.end > source.start, source.end <= original.utf16.count,
                      target.start >= 0, target.end > target.start, target.end <= translation.utf16.count else { return false }
                let sourceRange = NSRange(location: source.start, length: source.end-source.start)
                let targetRange = NSRange(location: target.start, length: target.end-target.start)
                guard Range(sourceRange, in: original) != nil, Range(targetRange, in: translation) != nil,
                      (original as NSString).substring(with: sourceRange) == entry.source,
                      Set(entry.targets) == Set([(translation as NSString).substring(with: targetRange)]) else { return false }
                guard !entries.contains(where: { guardEntry in
                    (guardEntry.unresolvedNativeSenses || guardEntry.protectInner) &&
                        sourceOccurrences(guardEntry, in: original, boundaries: sourceBoundaries).contains { whole in
                            (guardEntry.unresolvedNativeSenses && whole == sourceRange) ||
                                (guardEntry.protectInner && whole != sourceRange &&
                                    NSIntersectionRange(whole, sourceRange) == sourceRange)
                        }
                }) else { return false }
                return !primary.spans.contains { span in
                    NSIntersectionRange(sourceRange, span.range).length > 0 ||
                        NSIntersectionRange(targetRange, span.targetRange).length > 0
                }
            }
            // Density is applied once to the combined candidates.
            return align(original: original, translation: translation, entries: entries + additions, density: density,
                targetLanguage: targetLanguage, sourceBoundaries: sourceBoundaries,
                targetBoundaries: targetBoundaries, sourceTokenCount: sourceTokenCount, sourceUnitTokenCounts: sourceUnitTokenCounts)
        }
        // Use the installed Swift platform Character boundaries. Valid UTF16
        // endpoints alone need not bound a complete user-perceived character.
        let sourceGraphemes = Set(original.indices.map { $0.utf16Offset(in: original) } + [original.utf16.count])
        let targetGraphemes = Set(translation.indices.map { $0.utf16Offset(in: translation) } + [translation.utf16.count])
        let protected = matches(#"https?://\S+|www\.\S+|[\w.+-]+@[\w.-]+\.[\p{L}]{2,}|```[\s\S]*?```|`[^`]*`|[@#][\p{L}\p{N}_]+|\p{N}+(?:[.,:]\p{N}+)*"#, in: original)
        let protectedTarget = matches(#"https?://\S+|www\.\S+|[\w.+-]+@[\w.-]+\.[\p{L}]{2,}|```[\s\S]*?```|`[^`]*`|[@#][\p{L}\p{N}_]+|\p{N}+(?:[.,:]\p{N}+)*"#, in: translation)
        let sentenceStops = matches("[.!?。！？\\n]", in: original).filter { stop in !protected.contains { NSIntersectionRange($0, stop).length > 0 } }
        let supported = Set(entries.indices.filter { index in
            let entry = entries[index]
            guard let range = sourceOccurrences(entry, in: original, boundaries: sourceBoundaries).first else { return false }
            let lower = sentenceStops.last(where: { NSMaxRange($0) <= range.location }).map(NSMaxRange) ?? 0
            let upper = sentenceStops.first(where: { $0.location >= NSMaxRange(range) })?.location ?? original.utf16.count
            return entry.contextHints.contains { hint in
                !hint.isEmpty && hint.utf16.count <= 64 && occurrences(hint, in: original, boundaries: sourceBoundaries).contains { cue in
                    cue.location >= lower && NSMaxRange(cue) <= upper && NSIntersectionRange(cue, range).length == 0 &&
                    !protected.contains { NSIntersectionRange($0, cue).length > 0 }
                }
            }
        })
        // Retain lexical claims even when a repeated word or missing reading
        // makes that entry ineligible for display. Dropping it first can make
        // another, incorrect source word appear to own its translated token.
        let claims = entries.map { entry -> (source: [NSRange], target: Set<NSRange>) in
            guard !entry.source.isEmpty, entry.source.utf16.count <= 128 else { return ([], []) }
            let source = sourceOccurrences(entry, in: original, boundaries: sourceBoundaries)
            guard !source.isEmpty else { return ([], []) }
            let target = Set(Set(entry.targets).flatMap { value -> [NSRange] in
                guard !value.isEmpty, value.utf16.count <= 128 else { return [] }
                return targetOccurrences(entry,value:value,in:translation,boundaries:targetBoundaries)
            })
            return (source, target)
        }
        var candidates: [(span: ImmersionSpan, targetRange: NSRange, entry: Int)] = []
        for (index, entry) in entries.enumerated() where !entry.source.isEmpty && entry.source.utf16.count <= 128 {
            let sourceMatches = claims[index].source
            guard sourceMatches.count == 1, let range = sourceMatches.first,
                  !protected.contains(where: { NSIntersectionRange($0, range).length > 0 }) else { continue }
            // Native source evidence survives a missing pivot translation.
            // Explicitly assessed scopes are qualified separately.
            if entry.sourceScope == nil && entries.enumerated().contains(where: { offset, guardEntry in
                claims[offset].source.contains { whole in
                    (guardEntry.unresolvedNativeSenses && whole == range) ||
                    (guardEntry.protectInner && whole.location <= range.location &&
                     NSMaxRange(whole) >= NSMaxRange(range) && whole != range)
                }
            }) { continue }
            // More than one viable sense, or repeated target occurrences, abstains.
            let targetMatches = claims[index].target
            guard targetMatches.count == 1, let targetRange = targetMatches.first,
                  !protectedTarget.contains(where: { NSIntersectionRange($0, targetRange).length > 0 }) else { continue }
            guard sourceGraphemes.contains(range.location), sourceGraphemes.contains(NSMaxRange(range)),
                  targetGraphemes.contains(targetRange.location), targetGraphemes.contains(NSMaxRange(targetRange)) else { continue }
            let targetSurface = (translation as NSString).substring(with: targetRange)
            let sourceSurface = (original as NSString).substring(with: range)
            let needsReading = ["ar", "zh", "ja", "ko"].contains(targetLanguage?.components(separatedBy: "-")[0] ?? "")
            // Shared ideographs can have different readings (Chinese/Japanese
            // 水). A qualified target scope still teaches that pronunciation.
            guard sourceSurface.caseInsensitiveCompare(targetSurface) != .orderedSame ||
                  (needsReading && entry.targetScope != nil) else { continue }
            let readings = Set(entry.romanizations.filter { Self.lookupKey($0.key) == Self.lookupKey(targetSurface) }.values.flatMap { $0 })
            let reading = readings.count == 1 ? readings.first : nil
            if needsReading {
                guard let reading, !reading.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                      reading.utf16.count <= 256, Self.readableRomanization(reading) else { continue }
            }
            candidates.append((ImmersionSpan(range: range, original: sourceSurface, translated: targetSurface,
                targetRange: targetRange, romanization: needsReading ? reading : nil), targetRange, index))
        }
        // A translated token cannot be claimed by two disjoint source spans.
        let unambiguous = candidates.filter { candidate in
            !claims.enumerated().contains { index, claim in
                if claim.source.contains(candidate.span.range) {
                    if claim.target.contains(where: { $0 != candidate.targetRange }) { return true }
                    if let reading = candidate.span.romanization, claim.target.contains(candidate.targetRange) {
                        let alternatives = entries[index].romanizations.filter { Self.lookupKey($0.key) == Self.lookupKey(candidate.span.translated) }.values.flatMap { $0 }
                        if alternatives.contains(where: { $0 != reading }) { return true }
                    }
                }
                return claim.source.contains { other in NSIntersectionRange(other, candidate.span.range).length == 0 && !protected.contains { NSIntersectionRange($0, other).length > 0 } } &&
                    claim.target.contains { NSIntersectionRange($0, candidate.targetRange).length > 0 }
            } && !candidates.contains { other in
                (other.span.range == candidate.span.range && (other.targetRange != candidate.targetRange || other.span.romanization != candidate.span.romanization)) ||
                (other.span.range != candidate.span.range &&
                NSIntersectionRange(other.span.range, candidate.span.range).length == 0 &&
                NSIntersectionRange(other.targetRange, candidate.targetRange).length > 0)
            }
        }.filter { candidate in
            // A provider choosing one surface does not resolve a dictionary's
            // multiple meanings. Require a local cue, retaining all rival claims.
            !entries[candidate.entry].requiresContext || supported.contains(candidate.entry)
        }.filter { candidate in
            // Only veto after ambiguity checks. Removing a rival must never turn
            // an otherwise ambiguous translation into an accepted replacement.
            !supported.contains { index in
                Self.lookupKey(entries[index].source) == Self.lookupKey(entries[candidate.entry].source) &&
                !claims[index].target.contains(candidate.targetRange)
            }
        }.sorted { a, b in
            a.span.range.length == b.span.range.length ? a.span.range.location < b.span.range.location : a.span.range.length > b.span.range.length
        }
        let wordCount = max(1, sourceTokenCount ?? matches(#"[\p{L}\p{M}]+"#, in: original).count)
        // Prefer the qualified complete compound to its nested noun even
        // when a low density would otherwise fit only the shorter fragment.
        let complete = unambiguous.filter { child in !unambiguous.contains { parent in
            entries[parent.entry].sourceScope != nil && entries[parent.entry].targetScope != nil &&
                parent.span.range.length > child.span.range.length &&
                NSIntersectionRange(parent.span.range, child.span.range) == child.span.range &&
                NSIntersectionRange(parent.targetRange, child.targetRange) == child.targetRange
        } }
        let budget = max(1, Int(Double(wordCount) * min(density, 1)))
        // Only the exact-reference partial producer supplies native per-unit
        // costs. Unknown costs in that mode abstain, NEVER estimate via regex.
        // The legacy complete matcher keeps its existing default cost policy.
        let costed = complete.compactMap { candidate -> (span: ImmersionSpan, count: Int)? in
            let count: Int
            if let sourceUnitTokenCounts {
                guard let native = sourceUnitTokenCounts[candidate.span.range], native > 0, native <= wordCount else { return nil }
                count = native
            } else { count = max(1, matches(#"[\p{L}\p{M}]+"#, in: candidate.span.original).count) }
            return (candidate.span, count)
        }
        var selected: [ImmersionSpan] = []
        var usedWords = 0
        for candidate in costed {
            let count = candidate.count
            guard usedWords + count <= budget,
                  !selected.contains(where: { NSIntersectionRange($0.range, candidate.span.range).length > 0 }) else { continue }
            selected.append(candidate.span)
            usedWords += count
        }
        // Keep one complete vocabulary item when a low density rounds below
        // its word count. Only candidates that passed every meaning check
        // above participate; zero density still exits before this point.
        if selected.isEmpty, let smallest = costed.min(by: { a, b in
            a.count == b.count ? a.span.range.location < b.span.range.location : a.count < b.count
        }) { selected.append(smallest.span) }
        return ImmersionResult(original: original, translation: translation, spans: selected.sorted { $0.range.location < $1.range.location })
    }

    private func sourceOccurrences(_ entry: VocabularyEntry, in original: String, boundaries: Set<Int>?) -> [NSRange] {
        guard let scope=entry.sourceScope else { return occurrences(entry.source,in:original,boundaries:boundaries) }
        guard scope.original==original, scope.start>=0,scope.end>scope.start,scope.end<=original.utf16.count else {return []}
        let range=NSRange(location:scope.start,length:scope.end-scope.start)
        guard Range(range,in:original) != nil,(original as NSString).substring(with:range)==entry.source else {return []}
        return [range]
    }

    private func targetOccurrences(_ entry: VocabularyEntry,value: String,in translation: String,boundaries: Set<Int>?) -> [NSRange] {
        if let scope=entry.targetScope {
            guard entry.sourceScope != nil,scope.translation==translation,
                  scope.start>=0,scope.end>scope.start,scope.end<=translation.utf16.count else {return []}
            let range=NSRange(location:scope.start,length:scope.end-scope.start)
            guard Range(range,in:translation) != nil,(translation as NSString).substring(with:range)==value else {return []}
            return [range]
        }
        let plain=occurrences(value,in:translation,boundaries:boundaries)
        guard entry.sourceScope != nil,entry.targetForms.count<=16 else {return plain}
        var explicit:[NSRange]=[]
        for form in entry.targetForms where form.target==value && form.surface.utf16.count<=256 {
            guard form.start>=0,form.end>form.start,form.end<=form.surface.utf16.count else {continue}
            let local=NSRange(location:form.start,length:form.end-form.start)
            guard Range(local,in:form.surface) != nil,(form.surface as NSString).substring(with:local)==value else {continue}
            // Explicit attested forms alone also try their raw encoded surface;
            // generic normalized dictionary lookup remains unchanged. The exact
            // raw-length/whole-surface witness and final grapheme guard still apply.
            let wholeForms = Set(occurrences(form.surface,in:translation,boundaries:boundaries) +
                rawAttestedOccurrences(form.surface, in: translation, boundaries: boundaries))
            for whole in wholeForms {
                let actual=(translation as NSString).substring(with:whole)
                guard actual.utf16.count==form.surface.utf16.count,actual.replacingOccurrences(of:"’",with:"'").caseInsensitiveCompare(form.surface.replacingOccurrences(of:"’",with:"'")) == .orderedSame else {continue}
                let focus=NSRange(location:whole.location+local.location,length:local.length)
                guard Range(focus,in:translation) != nil,(translation as NSString).substring(with:focus).replacingOccurrences(of:"’",with:"'").caseInsensitiveCompare(value.replacingOccurrences(of:"’",with:"'")) == .orderedSame else {continue}
                explicit.append(focus)
            }
        }
        return Array(Set(plain+explicit))
    }

    private func rawAttestedOccurrences(_ surface: String, in text: String, boundaries: Set<Int>?) -> [NSRange] {
        let raw = NSRegularExpression.escapedPattern(for: surface)
        guard !raw.isEmpty else { return [] }
        if let boundaries {
            return matches(raw, in: text, options: [.caseInsensitive]).filter {
                boundaries.contains($0.location) && boundaries.contains(NSMaxRange($0))
            }
        }
        return matches("(?<![\\p{L}\\p{M}\\p{N}_])" + raw + "(?![\\p{L}\\p{M}\\p{N}_])",
                       in: text, options: [.caseInsensitive])
    }

    private static func readableRomanization(_ value: String) -> Bool {
        // Standard Latin-script transliteration may retain tone/length marks.
        // IPA and phonetic extensions are not a reading interface.
        guard value.range(of: #"\p{Latin}"#, options: .regularExpression) != nil,
              value.range(of: #"^[\p{Latin}\p{M} '’.-]+$"#, options: .regularExpression) != nil else { return false }
        return !value.unicodeScalars.contains { (0x0250...0x02FF).contains($0.value) || (0x1D00...0x1DBF).contains($0.value) }
    }

    private func occurrences(_ phrase: String, in text: String, boundaries: Set<Int>? = nil) -> [NSRange] {
        let escaped = Self.lookupKey(phrase).unicodeScalars.map { scalar in
            if scalar.value==0x27 || scalar.value==0x2019 {return "['’]"}
            let literal = NSRegularExpression.escapedPattern(for: String(scalar))
            return (0x0620...0x064A).contains(scalar.value) ? literal + "[\\u0640\\u064B-\\u0652\\u0670]*" : literal
        }.joined()
        guard !escaped.isEmpty else { return [] }
        if let boundaries {
            return matches(escaped, in: text, options: [.caseInsensitive]).filter { boundaries.contains($0.location) && boundaries.contains(NSMaxRange($0)) }
        }
        return matches("(?<![\\p{L}\\p{M}\\p{N}_])" + escaped + "(?![\\p{L}\\p{M}\\p{N}_])", in: text, options: [.caseInsensitive])
    }
    public static func lookupKey(_ value: String) -> String {
        String(String.UnicodeScalarView(value.precomposedStringWithCanonicalMapping.lowercased().unicodeScalars.filter {
            $0.value != 0x0640 && !(0x064B...0x0652).contains($0.value) && $0.value != 0x0670
        }))
    }
    private func matches(_ pattern: String, in text: String, options: NSRegularExpression.Options = []) -> [NSRange] {
        guard let regex = try? NSRegularExpression(pattern: pattern, options: options) else { return [] }
        return regex.matches(in: text, range: NSRange(location: 0, length: text.utf16.count)).map(\.range)
    }
}
