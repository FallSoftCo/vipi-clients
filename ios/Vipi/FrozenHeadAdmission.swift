import Foundation
import VipiCore

/// Conditional source-name-only evidence, never display permission. No caller is
/// installed. Source-key enumeration and baseline production remain external.
struct FrozenHeadAdmission {
    struct KeyScope {
        let original: String
        let focus: NSRange
        let keys: [String]
        let identity: String
        // Caller describes the actual producer; an all-spelling diagnostic is not
        // the frozen eligible-current-head producer and must remain labelled so.
        let basis: String
    }
    struct HeadEvidence {
        let headID: String
        let originalContext: NSRange?
        let target: String
        let originalReadingsJSON: String
        let supportedTuples: [FrozenContextPack.Link]
        let rejectionReasons: [String]
        var conditionallyEligible: Bool { rejectionReasons.isEmpty && !supportedTuples.isEmpty }
    }
    struct Assessment {
        let original: String
        let focus: NSRange
        let packSHA256: String
        let keyScopeIdentity: String, keyScopeBasis: String
        let chosenRuleID: String?
        let learnedContext: NSRange?
        let classification: String
        let knowledgeIDs: [String]
        let heads: [HeadEvidence]
        let rejectionReasons: [String]
        let qualificationLimits: [String]
        // No SourceLookupEvidence, outputID, approvedOutputs or density argument.
    }
    private let tokenizer: FrozenContextTokenizer
    private let sourceCase: FrozenSourceCase
    init() throws { tokenizer = try FrozenContextTokenizer(); sourceCase = try FrozenSourceCase() }
    private func equal(_ a: String, _ b: String) -> Bool { a.utf8.elementsEqual(b.utf8) }
    private func dictionaryKey(_ value: String) -> String { ImmersionEngine.lookupKey(value) }
    private func classify(_ source: String, pack: FrozenContextPack) throws -> (String,[String]) {
        let words = try tokenizer.tokenize(source).filter { tokenizer.originalHasAlphabeticScalar($0.original) }.map(\.normalized)
        let nonfunction = words.filter { !pack.evidence.isFunction($0) }
        let anchors = nonfunction.filter { !pack.evidence.roles(for:$0).isDisjoint(with:["noun","adj","adv","verb"]) }
        let category = !anchors.isEmpty ? "content" : !nonfunction.isEmpty ? "unresolved" : "function"
        let ids = nonfunction.map { pack.evidence.family(for:$0) ?? "unmapped:"+$0 }
        return (category,Dictionary(grouping:ids,by:{Data($0.utf8)}).values.map{$0[0]}.sorted())
    }
    private func dictionaryIdentity(_ pack: FrozenContextPack, _ key: String) throws -> String {
        let metadata = try JSONDecoder().decode([String:String].self,from:Data((pack.metadata["dictionary_en_metadata_json"] ?? "").utf8))
        return try JSONDecoder().decode(String.self,from:Data((metadata[key] ?? "").utf8))
    }
    func assess(pack: FrozenContextPack, original: String, focus: NSRange, keyScope: KeyScope,
                recognition: LexicalSourceRecognition.Snapshot, role: EnglishSourceRoleProvider.Snapshot,
                knownFamilyIDs: [String]) throws -> Assessment {
        guard original.utf16.count <= 16_384, knownFamilyIDs.count <= 65_536,
              knownFamilyIDs.allSatisfy({ !$0.isEmpty && $0.utf8.count <= 4096 }),
              keyScope.keys.count <= 256, !keyScope.identity.isEmpty, keyScope.identity.utf8.count <= 256,
              keyScope.basis.utf8.count <= 1024 else { throw FrozenContextPack.Failure.bound }
        var reasons: [String] = []
        let limits = ["Conditional research evidence only; meaning is not certified.",
            "Caller key scope is explicit; this adapter does not recreate original head_keys or baseline candidate producer.",
            "Native source masks and Apple occurrence roles differ from frozen Python masks/OpenNLP observations.",
            "Pinned Python Unicode15 scalar case predicates; native Foundation NFC remains qualified only on retained probes.",
            "No density/competition/selector/presentation admission or fallback after the chosen winner."]
        func finish(_ winner: FrozenContextPack.Winner?, _ category: String = "unassessed", _ knowledge: [String] = [], _ heads: [HeadEvidence] = []) -> Assessment {
            .init(original:original,focus:focus,packSHA256:pack.contentSHA256,keyScopeIdentity:keyScope.identity,
                  keyScopeBasis:keyScope.basis,chosenRuleID:winner?.rule.id,learnedContext:winner?.contextRange,
                  classification:category,knowledgeIDs:knowledge,heads:heads,rejectionReasons:reasons,qualificationLimits:limits)
        }
        guard equal(keyScope.original,original), keyScope.focus == focus,
              LexicalSourceRecognition.valid(focus,in:original) else { reasons.append("invalid_or_stale_key_scope"); return finish(nil) }
        let native = LocalImmersion.words(original,language:"en")
        guard role.matches(original:original,language:"en",wordRanges:native,protectedRanges:recognition.suppliedProtection),
              recognition.matches(original:original,language:"en",dictionaryRelease:try dictionaryIdentity(pack,"release_id"),
                  dictionaryInventory:try dictionaryIdentity(pack,"source_inventory_sha256"),protectedRanges:role.suppliedProtection),
              native.contains(focus) else { reasons.append("snapshot_or_dictionary_identity_mismatch"); return finish(nil) }
        // Winner is fixed BEFORE role/head/known checks; never ask for the next rule.
        let match = try pack.assess(original:original,nativeWordRanges:native,focus:focus,sourceKeys:keyScope.keys)
        guard let winner = match.winner else { reasons.append("no_qualified_context_rule"); return finish(nil) }
        let source = (original as NSString).substring(with:focus)
        let (category,knowledge) = try classify(source,pack:pack)
        let known = Set(knownFamilyIDs.map { Data($0.utf8) })
        if !knowledge.isEmpty && knowledge.allSatisfy({known.contains(Data($0.utf8))}) { reasons.append("known_families") }
        if category != "content" { reasons.append("not_content_classified") }
        if !sourceCase.isLower(source) { reasons.append("requires_lowercase_source") }
        let observations = role.observations.filter { $0.range == focus }
        if role.status != .ready || observations.count != 1 || observations.first?.role != .noun { reasons.append("actual_apple_noun_unavailable") }
        if observations.first?.nounEligible != true { reasons.append("source_role_or_name_protection") }
        if recognition.hasStructuralProtection(at:focus) { reasons.append("native_source_structural_protection") }
        if role.protectedRanges.contains(where:{NSIntersectionRange($0,focus).length > 0}) { reasons.append("supplied_or_detected_name_protection") }
        let exactUnits = recognition.units.filter { $0.range == focus }
        guard !exactUnits.isEmpty else { reasons.append("no_current_dictionary_focus"); return finish(winner,category,knowledge) }
        if !exactUnits.contains(where:{$0.hasNameGuard && $0.sourceBlocked && !$0.targetBlocked}) { reasons.append("not_source_name_only_guard") }
        if exactUnits.contains(where:{$0.targetBlocked || ($0.sourceBlocked && !$0.hasNameGuard)}) { reasons.append("other_current_dictionary_guard") }
        guard let windows = ReviewedFrameLookup.windows(original,language:"en") else { reasons.append("native_context_window_unavailable"); return finish(winner,category,knowledge) }
        let contextWindows = Set(windows.values.flatMap{$0})
        let tokens = try tokenizer.tokenize(original)
        guard let position = tokens.firstIndex(where:{$0.range == focus}) else { reasons.append("not_exact_single_research_token"); return finish(winner,category,knowledge) }
        var evidence: [HeadEvidence] = []
        for headID in winner.rule.headIDs {
            guard let head = pack.heads[headID] else { throw FrozenContextPack.Failure.identity }
            var rejected = reasons, context: NSRange?, supported: [FrozenContextPack.Link] = []
            if head.focus.count != 2 || head.focus[1]-head.focus[0] != 1 { rejected.append("not_single_token_original_head") }
            let start = position-head.focus[0], after = start+head.tokens.count
            if start >= 0 && after <= tokens.count && head.focus[1]-head.focus[0] == 1 {
                let actual = tokens[start..<after]
                let range = NSRange(location:tokens[start].range.location,length:NSMaxRange(tokens[after-1].range)-tokens[start].range.location)
                if zip(actual.map(\.normalized),head.tokens).allSatisfy({equal($0,$1)}),
                   equal(try tokenizer.normalize((original as NSString).substring(with:range)),head.sourceKey), contextWindows.contains(range) { context = range }
            }
            if context == nil { rejected.append("original_head_context_missing_or_not_native_window") }
            let positions = try JSONDecoder().decode([String].self,from:Data(head.posJSON.utf8))
            if !positions.contains("noun") { rejected.append("original_head_noun_role_missing") }
            if !equal(head.target,winner.rule.target) { rejected.append("head_target_not_winner") }
            if equal(try tokenizer.normalize(source),try tokenizer.normalize(head.target)) { rejected.append("identical_target_face") }
            if head.target.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty { rejected.append("empty_target_face") }
            for link in pack.evidence.linksByRuleHead[.init(ruleID:winner.rule.id,headID:headID)] ?? [] {
                guard let sf = pack.evidence.forms[link.sourceFormID], let tf = pack.evidence.forms[link.targetFormID],
                      let st = pack.evidence.terms[link.sourceTermID], let tt = pack.evidence.terms[link.targetTermID] else { throw FrozenContextPack.Failure.identity }
                guard sf.language == "en", tf.language == "es", sf.partOfSpeech == "noun", tf.partOfSpeech == "noun",
                      sf.complete, tf.complete, (1...2).contains(sf.mode), (1...2).contains(tf.mode), sf.number == tf.number,
                      Set(sf.originalReasons) == ["dictionary_guard"], tf.originalReasons.isEmpty, sf.targetSafe, tf.targetSafe,
                      st.eligible, tt.eligible, st.explicit, tt.explicit, st.originalReasons.isEmpty, tt.originalReasons.isEmpty,
                      st.senseID == tt.senseID, equal(dictionaryKey(tf.surface),dictionaryKey(head.target)),
                      equal(dictionaryKey(sf.surface),dictionaryKey(source)) else { continue }
                // Exact current raw form identity; mode0/nil focus never participates.
                let current = exactUnits.flatMap(\.forms).contains { form in
                    form.intrinsicRange == sf.range && form.lexemeID == String(sf.lexeme) && equal(form.written,sf.surface) &&
                    form.number == sf.number && form.mode == sf.mode && form.features == Set(sf.features) &&
                    form.partOfSpeech == sf.partOfSpeech && form.sourceSafe == sf.sourceSafe && form.targetSafe == sf.targetSafe
                }
                if !current { continue }
                // Historical source capitalization guard: current focus is lower;
                // dictionary-initial uppercase/titlecase remains rejected.
                if !equal(sf.surface,source), sourceCase.firstIsUpper(sf.surface) { continue }
                supported.append(link)
            }
            if supported.isEmpty { rejected.append("no_exact_original_supported_form_term_tuple") }
            evidence.append(.init(headID:headID,originalContext:context,target:head.target,originalReadingsJSON:head.readingsJSON,
                supportedTuples:supported,rejectionReasons:Array(Set(rejected)).sorted()))
        }
        if winner.rule.headIDs.isEmpty { reasons.append("winner_has_no_supported_original_head") }
        return finish(winner,category,knowledge,evidence)
    }
}
