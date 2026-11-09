import Foundation
import SQLite3

extension FrozenContextPack {
    struct Form {
        let id: String, language: String, lexeme: Int, surface: String
        let range: NSRange, number: Int, mode: Int, features: [String]
        let headword: String, partOfSpeech: String
        let sourceSafe: Bool, targetSafe: Bool, complete: Bool
        let originalReasons: [String], sourceRecordSHA256: String
    }
    struct Term {
        let id: String, senseID: String, reading: String
        let eligible: Bool, explicit: Bool
        let qualifiersJSON: String, originalReasons: [String], sourceRecordSHA256: String
    }
    struct Link: Hashable {
        let ruleID: String, headID: String, sourceFormID: String, targetFormID: String
        let sourceTermID: String, targetTermID: String
    }
    struct RuleHead: Hashable { let ruleID: String, headID: String }
    struct Evidence {
        let forms: [String: Form], terms: [String: Term]
        let links: [Link], linksByRuleHead: [RuleHead: [Link]]
        // UTF8 keys avoid Swift canonical-equivalent String-key conflation.
        let families: [Data: String], roles: [Data: Set<String>], functionWords: Set<Data>
        func family(for source: String) -> String? { families[Data(source.utf8)] }
        func roles(for source: String) -> Set<String> { roles[Data(source.utf8)] ?? [] }
        func isFunction(_ source: String) -> Bool { functionWords.contains(Data(source.utf8)) }
    }
    private static func hashID(_ value: String) -> Bool {
        value.utf8.count == 64 && value.utf8.allSatisfy { (48...57).contains($0) || (97...102).contains($0) }
    }
    private static func boolean(_ s: OpaquePointer, _ column: Int32) throws -> Bool {
        let n = try integer(s, column); guard n == 0 || n == 1 else { throw Failure.malformed }; return n == 1
    }
    private static func boundedStrings(_ s: OpaquePointer, _ column: Int32, maximum: Int = 256) throws -> [String] {
        let raw = try text(s, column); guard raw.utf8.count <= 16_384 else { throw Failure.bound }
        let values = try strings(raw)
        guard values.count <= maximum, values.allSatisfy({ $0.utf8.count <= 4096 }) else { throw Failure.bound }; return values
    }
    static func readEvidence(_ db: OpaquePointer, rules: [Rule], heads: [String: Head]) throws -> Evidence {
        var forms: [String: Form] = [:], terms: [String: Term] = [:]
        try rows(db,"SELECT id,language,lexeme,surface,form_range_json,number,mode,features_json,headword,pos,source_safe,target_safe,complete,original_reasons_json,source_record_sha256 FROM forms ORDER BY id",maximum:4096) { s in
            let id = try text(s,0), language = try text(s,1), lexeme = try integer(s,2), surface = try text(s,3)
            let range = try JSONDecoder().decode([Int].self,from:Data(text(s,4).utf8))
            let number = try integer(s,5), mode = try integer(s,6), complete = try boolean(s,12)
            let record = try text(s,14), pos = try text(s,9)
            guard hashID(id), hashID(record), forms[id] == nil, ["en","es"].contains(language), lexeme >= 0,
                  !surface.isEmpty, surface.utf16.count <= 1024, range.count == 2, range[0] == 0,
                  range[1] == surface.utf16.count, complete, (1...2).contains(mode), (0...2).contains(number), pos == "noun" else { throw Failure.malformed }
            forms[id] = try .init(id:id,language:language,lexeme:lexeme,surface:surface,range:.init(location:0,length:range[1]),
                number:number,mode:mode,features:boundedStrings(s,7),headword:text(s,8),partOfSpeech:pos,
                sourceSafe:boolean(s,10),targetSafe:boolean(s,11),complete:complete,
                originalReasons:boundedStrings(s,13),sourceRecordSHA256:record)
        }
        try rows(db,"SELECT id,sense_id,reading,eligible,explicit,qualifiers_json,original_reasons_json,source_record_sha256 FROM terms ORDER BY id",maximum:8192) { s in
            let id = try text(s,0), sense = try text(s,1), reading = try text(s,2), qualifiers = try text(s,5), record = try text(s,7)
            guard hashID(id), hashID(sense), hashID(record), terms[id] == nil, reading.utf16.count <= 2048,
                  qualifiers.utf8.count <= 16384,
                  (try JSONSerialization.jsonObject(with:Data(qualifiers.utf8))) is [String:Any] else { throw Failure.malformed }
            terms[id] = try .init(id:id,senseID:sense,reading:reading,eligible:boolean(s,3),explicit:boolean(s,4),
                qualifiersJSON:qualifiers,originalReasons:boundedStrings(s,6),sourceRecordSHA256:record)
        }
        let ruleMap = Dictionary(uniqueKeysWithValues:rules.map { ($0.id,$0) })
        var links: [Link] = [], seen = Set<Link>()
        try rows(db,"SELECT rule_id,head_id,source_form,target_form,source_term,target_term FROM links ORDER BY rule_id,head_id,source_form,target_form,source_term,target_term",maximum:32768) { s in
            let link = try Link(ruleID:text(s,0),headID:text(s,1),sourceFormID:text(s,2),targetFormID:text(s,3),sourceTermID:text(s,4),targetTermID:text(s,5))
            guard seen.insert(link).inserted, let rule = ruleMap[link.ruleID], rule.headIDs.contains(link.headID),
                  let head = heads[link.headID], head.target.utf8.elementsEqual(rule.target.utf8),
                  let sf = forms[link.sourceFormID], let tf = forms[link.targetFormID],
                  let st = terms[link.sourceTermID], let tt = terms[link.targetTermID],
                  sf.language == "en", tf.language == "es", sf.number == tf.number,
                  sf.partOfSpeech == tf.partOfSpeech, st.senseID == tt.senseID,
                  st.eligible, tt.eligible, st.explicit, tt.explicit,
                  st.originalReasons.isEmpty, tt.originalReasons.isEmpty else { throw Failure.malformed }
            links.append(link)
        }
        var families: [Data:String] = [:], roles: [Data:Set<String>] = [:], function = Set<Data>()
        try rows(db,"SELECT source,family_id FROM known_families ORDER BY source",maximum:32768) { s in
            let source = try text(s,0), family = try text(s,1), key = Data(source.utf8)
            guard !source.isEmpty, source.utf8.count <= 4096, !family.isEmpty, family.utf8.count <= 4096, families[key] == nil else { throw Failure.malformed }; families[key] = family
        }
        try rows(db,"SELECT source,roles_json FROM source_roles ORDER BY source",maximum:32768) { s in
            let source = try text(s,0), key = Data(source.utf8), list = try boundedStrings(s,1)
            guard !source.isEmpty, source.utf8.count <= 4096, roles[key] == nil else { throw Failure.malformed }; roles[key] = Set(list)
        }
        try rows(db,"SELECT source FROM function_words ORDER BY source",maximum:4096) { s in
            let source = try text(s,0)
            guard !source.isEmpty, source.utf8.count <= 4096, function.insert(Data(source.utf8)).inserted else { throw Failure.malformed }
        }
        guard forms.count == 326, terms.count == 651, links.count == 5328, families.count == 3011,
              roles.count == 6384, function.count == 87 else { throw Failure.identity }
        return .init(forms:forms,terms:terms,links:links,
            linksByRuleHead:Dictionary(grouping:links,by:{RuleHead(ruleID:$0.ruleID,headID:$0.headID)}),
            families:families,roles:roles,functionWords:function)
    }
}
