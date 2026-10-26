import Foundation
import SQLite3
import VipiCore

/// Shared by authenticated downloads and app-signed bundled context data.
enum ReviewedContextLookup {
    static func entries(db: OpaquePointer, original text: String, source: String, target: String) throws -> [VocabularyEntry] {
        func lookup(_ input:String) throws -> [ContextMapping] {
            var statement:OpaquePointer?
            let sql="SELECT m.payload FROM context_inputs i JOIN mappings m ON m.id=i.mapping_id WHERE i.input=? ORDER BY m.id LIMIT 257"
            guard sqlite3_prepare_v2(db,sql,-1,&statement,nil) == SQLITE_OK else {throw VocabularyPackError.storage}
            defer {sqlite3_finalize(statement)}
            guard sqlite3_bind_text(statement,1,input,-1,unsafeBitCast(-1,to:sqlite3_destructor_type.self)) == SQLITE_OK else {throw VocabularyPackError.storage}
            var mappings:[ContextMapping]=[];var status=sqlite3_step(statement)
            while status == SQLITE_ROW {
                guard let raw=sqlite3_column_text(statement,0) else {throw VocabularyPackError.invalid}
                mappings.append(try ReviewedContextRecord.mapping(Data(String(cString:raw).utf8),source:source,target:target))
                guard mappings.count<=256 else {throw VocabularyPackError.invalid}
                status=sqlite3_step(statement)
            }
            guard status == SQLITE_DONE else {throw VocabularyPackError.storage}
            return mappings
        }
        let whole=try lookup(text)
        // A known whole-message context, including an ambiguous one,
        // never falls through to weaker sentence evidence.
        if !whole.isEmpty {return ContextMappingMatcher.entries(original:text,source:source,target:target,mappings:whole)}
        var entries:[VocabularyEntry]=[];var matched=0
        for sentence in LocalImmersion.sentences(text,language:source) where sentence != NSRange(location:0,length:text.utf16.count) {
            let fragment=(text as NSString).substring(with:sentence)
            let mappings=try lookup(fragment);matched+=mappings.count
            guard matched<=256 else {return []}
            for entry in ContextMappingMatcher.entries(original:fragment,source:source,target:target,mappings:mappings) {
                guard let scope=entry.sourceScope,scope.original==fragment else {throw VocabularyPackError.invalid}
                entries.append(.init(source:entry.source,targets:entry.targets,romanizations:entry.romanizations,
                    contextHints:entry.contextHints,requiresContext:entry.requiresContext,
                    sourceScope:.init(original:text,start:sentence.location+scope.start,end:sentence.location+scope.end),targetForms:entry.targetForms))
            }
        }
        return entries
    }
}
