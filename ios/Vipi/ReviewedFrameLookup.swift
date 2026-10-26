import Foundation
import SQLite3
import VipiCore

enum ReviewedFrameLookup {
    private enum Limit:Error {case overflow}
    /// Native word windows inside complete sentences; no partial/truncated scan.
    static func windows(_ text:String,language:String) -> [String:[NSRange]]? {
        guard text.utf16.count<=32768 else {return nil}
        let sentences=LocalImmersion.sentences(text,language:language)
        if !text.isEmpty && sentences.isEmpty {return nil}
        var result:[String:[NSRange]]=[:];var count=0
        let stops=CharacterSet(charactersIn:".!?。！？;；\r\n")
        for sentence in sentences {
            let fragment=(text as NSString).substring(with:sentence)
            let words=LocalImmersion.words(fragment,language:language)
            for i in words.indices {
                var starts=[words[i].location]
                let word=(fragment as NSString).substring(with:words[i])
                if language=="fr",let apostrophe=word.firstIndex(where:{$0=="'" || $0=="’"}),
                   ["j","l","d","t","m","n","s","c","qu"].contains(String(word[..<apostrophe]).lowercased()) {
                    let body=word.index(after:apostrophe)
                    if body<word.endIndex {starts.append(words[i].location+word[..<body].utf16.count)}
                }
                for j in i..<min(words.count,i+8) {for start in starts {
                let range=NSRange(location:start,length:NSMaxRange(words[j])-start)
                if range.length>256 {continue}
                let input=(fragment as NSString).substring(with:range)
                if input.rangeOfCharacter(from:stops) != nil {continue}
                count+=1;if count>4096 {return nil}
                result[input,default:[]].append(NSRange(location:sentence.location+range.location,length:range.length))
            }}}
        }
        return result
    }
    private static func frame(_ data:Data,source:String,target:String) throws -> ContextFrame {
        struct Row:Decodable {
            let id:String,meaning:String,source_language:String,target_language:String,source:String,target:String,reading:String
            let source_parts:[[String:Part]],target_parts:[[String:Part]]
            enum Part:Decodable {
                case text(String),slot([String])
                init(from decoder:Decoder) throws {
                    let value=try decoder.singleValueContainer()
                    if let text=try? value.decode(String.self) {self = .text(text)}
                    else {self = .slot(try value.decode([String].self))}
                }
            }
        }
        guard data.count<=32768 else {throw VocabularyPackError.invalid}
        let row=try JSONDecoder().decode(Row.self,from:data)
        guard row.source_language==source,row.target_language==target,row.reading.utf16.count<=256 else {throw VocabularyPackError.invalid}
        func parts(_ values:[[String:Row.Part]],focus:String) throws -> [ContextPart] {
            let result=try values.map { part -> ContextPart in
                guard part.count==1,let (key,value)=part.first else {throw VocabularyPackError.invalid}
                switch(key,value) {
                case("literal",.text(let text)):return .literal(text)
                case("focus",.text(let text)):guard text==focus else {throw VocabularyPackError.invalid};return .focus(text)
                case("slot",.slot(let choices)):return .slot(choices)
                default:throw VocabularyPackError.invalid
                }
            }
            return result
        }
        return try .init(id:row.id,meaning:row.meaning,sourceLanguage:source,targetLanguage:target,
            sourceParts:parts(row.source_parts,focus:row.source),targetParts:parts(row.target_parts,focus:row.target),reading:row.reading)
    }
    static func entries(db:OpaquePointer,original:String,translation:String,source:String,target:String) throws -> [VocabularyEntry] {
        guard let left=windows(original,language:source),let right=windows(translation,language:target) else {return []}
        func query(_ sql:String,_ arguments:[String]) throws -> [(String,String,String)] {
            var statement:OpaquePointer?
            guard sqlite3_prepare_v2(db,sql,-1,&statement,nil)==SQLITE_OK else {throw VocabularyPackError.storage}
            defer {sqlite3_finalize(statement)}
            for (i,value) in arguments.enumerated() {
                guard sqlite3_bind_text(statement,Int32(i+1),value,-1,unsafeBitCast(-1,to:sqlite3_destructor_type.self))==SQLITE_OK else {throw VocabularyPackError.storage}
            }
            var rows:[(String,String,String)]=[];var status=sqlite3_step(statement)
            while status==SQLITE_ROW {
                guard let a=sqlite3_column_text(statement,0),let b=sqlite3_column_text(statement,1),let c=sqlite3_column_text(statement,2) else {throw VocabularyPackError.invalid}
                rows.append((String(cString:a),String(cString:b),String(cString:c)))
                if rows.count>256 {throw Limit.overflow};status=sqlite3_step(statement)
            }
            guard status==SQLITE_DONE else {throw VocabularyPackError.storage}
            return rows
        }
        func placeholders(_ count:Int) -> String {Array(repeating:"?",count:count).joined(separator:",")}
        var records:[String:ContextFrame]=[:],sourceHits:[String:Set<NSRange>]=[:],targetHits:[String:Set<NSRange>]=[:]
        do {
            var count=0;let inputs=left.keys.sorted()
            for offset in stride(from:0,to:inputs.count,by:200) {
                let batch=Array(inputs[offset..<min(offset+200,inputs.count)])
                let rows=try query("SELECT i.input,m.id,m.payload FROM source_inputs i JOIN mappings m ON m.id=i.mapping_id WHERE i.input IN (\(placeholders(batch.count))) LIMIT 257",batch)
                count+=rows.count;if count>256 {return []}
                for (input,id,payload) in rows {
                    if records[id]==nil {
                        let value=try frame(Data(payload.utf8),source:source,target:target)
                        guard value.id==id else {throw VocabularyPackError.invalid};records[id]=value
                    }
                    sourceHits[id,default:[]].formUnion(left[input,default:[]])
                }
            }
            let ids=records.keys.sorted();if ids.isEmpty {return []}
            count=0;let targets=right.keys.sorted()
            for offset in stride(from:0,to:targets.count,by:200) {
                let batch=Array(targets[offset..<min(offset+200,targets.count)])
                let rows=try query("SELECT input,mapping_id,'' FROM target_inputs WHERE input IN (\(placeholders(batch.count))) AND mapping_id IN (\(placeholders(ids.count))) LIMIT 257",batch+ids)
                count+=rows.count;if count>256 {return []}
                for (input,id,_) in rows {targetHits[id,default:[]].formUnion(right[input,default:[]])}
            }
            let hits=ids.map {ContextFrameHit(frame:records[$0]!,sourceWindows:Array(sourceHits[$0,default:[]]),targetWindows:Array(targetHits[$0,default:[]]))}
            return ContextFrameMatcher.entries(original:original,translation:translation,source:source,target:target,hits:hits)
        } catch Limit.overflow {return []}
    }
}
