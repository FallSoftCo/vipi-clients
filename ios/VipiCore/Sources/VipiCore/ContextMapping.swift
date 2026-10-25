import Foundation

/// Finite, authored context patterns. Slots remain in the original message.
public enum ContextPart: Sendable, Equatable {
    case literal(String), slot([String]), focus(String)
}
public struct ContextMapping: Sendable {
    public let id: String, meaning: String, sourceLanguage: String, targetLanguage: String
    public let parts: [ContextPart], targets: [String], readings: [String: [String]]
    public let targetForms: [VocabularyTargetForm]
    public init(id: String, meaning: String, sourceLanguage: String, targetLanguage: String,
                parts: [ContextPart], targets: [String], readings: [String: [String]] = [:], targetForms: [VocabularyTargetForm] = []) {
        self.id = id; self.meaning = meaning; self.sourceLanguage = sourceLanguage; self.targetLanguage = targetLanguage
        self.parts = parts; self.targets = targets; self.readings = readings
        self.targetForms = targetForms
    }
}
/// Exact context/scope matching, separate from linguistic review of the data.
/// Supply a bounded indexed shortlist, not the whole language catalog.
public enum ContextMappingMatcher {
    private struct State: Hashable { let offset: Int; let focus: NSRange? }
    public static func entries(original: String, source: String, target: String, mappings: [ContextMapping]) -> [VocabularyEntry] {
        guard !original.isEmpty, original.utf16.count <= 16_384, mappings.count <= 256, source != target else { return [] }
        var groups: [NSRange: [ContextMapping]] = [:]
        for record in mappings {
            guard record.sourceLanguage == source, record.targetLanguage == target,
                  !record.id.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  !record.meaning.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  let focus = match(original, record: record) else { continue }
            groups[focus, default: []].append(record)
        }
        var entries: [VocabularyEntry] = []
        for (focus, group) in groups.sorted(by: { $0.key.location < $1.key.location }) {
            guard Set(group.map(\.meaning)).count == 1 else { continue }
            for record in group {
                let entry = VocabularyEntry(source: (original as NSString).substring(with: focus), targets: record.targets, romanizations: record.readings,
                    sourceScope: .init(original: original,start: focus.location,end: NSMaxRange(focus)),targetForms:record.targetForms)
                if !entries.contains(entry) { entries.append(entry) }
            }
        }
        return entries
    }
    private static func match(_ original: String, record: ContextMapping) -> NSRange? {
        guard (1...12).contains(record.parts.count), record.parts.filter({ if case .focus = $0 { return true }; return false }).count == 1,
              record.parts.contains(where: { if case .literal(let text) = $0 { return !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }; return false }),
              (1...16).contains(record.targets.count), record.targets.allSatisfy({ !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && $0.utf16.count <= 128 }) else { return nil }
        let text = original as NSString
        var states: Set<State> = [State(offset: 0,focus: nil)]
        for part in record.parts {
            let alternatives: [String]; let isFocus: Bool
            switch part {
            case .literal(let value): alternatives = [value]; isFocus = false
            case .focus(let value): alternatives = [value]; isFocus = true
            case .slot(let values): alternatives = values; isFocus = false
            }
            guard (1...32).contains(alternatives.count), alternatives.allSatisfy({ !$0.isEmpty && $0.utf16.count <= (isFocus ? 128 : 256) }) else { return nil }
            var next = Set<State>()
            for state in states { for value in alternatives {
                let range = NSRange(location: state.offset,length: value.utf16.count)
                guard NSMaxRange(range) <= text.length, Range(range,in: original) != nil,
                      text.substring(with: range) == value else { continue }
                next.insert(State(offset: NSMaxRange(range),focus: isFocus ? range : state.focus))
                if next.count > 128 { return nil }
            } }
            guard !next.isEmpty else { return nil }; states = next
        }
        let focuses = Set(states.filter { $0.offset == text.length }.compactMap(\.focus))
        return focuses.count == 1 ? focuses.first : nil
    }
}
