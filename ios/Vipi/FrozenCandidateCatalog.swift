import Foundation
import SQLite3
import CryptoKit

/// Immutable, externally pinned research catalog. No presentation permissions.
/// Keep one reader per verified identity; callers preserve the file while open.
final class FrozenCandidateCatalog {
    typealias Failure = FrozenContextPack.Failure
    struct Head {
        let id: String, key: String, contextID: String
        let ordinary: Bool, conditional: Bool
        let rank: Int
        let recordJSON: String, auditJSON: String
        let record: [String:Any], audit: [String:Any]
    }
    private let db: OpaquePointer
    let sha256: String, metadata: [String:String]
    let bundleIdentity: String, contextPackSHA256: String
    let manifest: [String:Any]
    static func digest(_ url: URL, maximum: Int) throws -> String {
        for suffix in ["-wal","-shm","-journal"] {
            guard !FileManager.default.fileExists(atPath:url.path+suffix) else { throw Failure.identity }
        }
        let f=try FileHandle(forReadingFrom:url);defer{try? f.close()};var hash=SHA256(),n=0
        while try autoreleasepool(invoking: { () throws -> Bool in
            guard let b=try f.read(upToCount:1<<20),!b.isEmpty else{return false}
            n+=b.count;guard n<=maximum else{throw Failure.bound}
            hash.update(data:b)
            return true
        }) {}
        return hash.finalize().map{String(format:"%02x",$0)}.joined()
    }
    static func hash(_ s:String)->String { SHA256.hash(data:Data(s.utf8)).map{String(format:"%02x",$0)}.joined() }
    init(url:URL,manifestURL:URL,manifestSHA256:String,contextPack:FrozenContextPack) throws {
        guard try Self.digest(manifestURL,maximum:1<<20)==manifestSHA256 else{throw Failure.identity}
        let m=try JSONSerialization.jsonObject(with:Data(contentsOf:manifestURL)) as? [String:Any]
        guard let m,m["schema"] as? String=="vipi.source-candidate-manifest.1",m["permission"] as? String=="disabled_research_only",
              let hash=m["database_sha256"] as? String,let counts=m["table_counts"] as? [String:Int],
              let dependencies=m["dependencies"] as? [String:[String:String]],
              dependencies["context_pack"]?["sha256"]==contextPack.contentSHA256,
              try Self.digest(url,maximum:256<<20)==hash else{throw Failure.identity}
        for lang in ["en","es"] {guard dependencies["dictionary_"+lang]?["sha256"]==contextPack.metadata["dictionary_"+lang+"_sha256"] else{throw Failure.identity}}
        guard (try url.resourceValues(forKeys:[.fileSizeKey])).fileSize==m["database_bytes"] as? Int else{throw Failure.identity}
        var pointer:OpaquePointer?;guard sqlite3_open_v2(url.path,&pointer,SQLITE_OPEN_READONLY|SQLITE_OPEN_NOMUTEX,nil)==SQLITE_OK,let pointer else{if let pointer{sqlite3_close(pointer)};throw Failure.sqlite}
        db=pointer;sha256=hash;manifest=m
        contextPackSHA256=contextPack.contentSHA256
        bundleIdentity=Self.hash(["vipi.candidate-bundle.1",manifestSHA256,hash,contextPack.contentSHA256,
            dependencies["dictionary_en"]!["sha256"]!,dependencies["dictionary_es"]!["sha256"]!,
            m["contract_sha256"] as? String ?? ""].joined(separator:"\n"))
        do {
            sqlite3_limit(db,SQLITE_LIMIT_LENGTH,262144);sqlite3_limit(db,SQLITE_LIMIT_ATTACHED,0)
            guard sqlite3_exec(db,"PRAGMA query_only=ON;PRAGMA trusted_schema=OFF;PRAGMA cache_size=-8192;BEGIN",nil,nil,nil)==SQLITE_OK else{throw Failure.sqlite}
            var app=0,version=0
            try Self.query(db,"PRAGMA application_id",[]){app=Int(sqlite3_column_int($0,0))}
            try Self.query(db,"PRAGMA user_version",[]){version=Int(sqlite3_column_int($0,0))}
            guard app==1447645257,version==1 else{throw Failure.schema}
            let tables=["metadata","candidates","head_keys","evidence","head_evidence","known_families","source_roles","function_words"]
            guard Set(counts.keys)==Set(tables) else{throw Failure.schema}
            for table in tables {guard let expected=counts[table],expected>=0,expected<=2_000_000,(table != "candidates" || expected<=65536) else{throw Failure.bound};var count=0;try Self.query(db,"SELECT count(*) FROM \(table)",[]){count=Int(sqlite3_column_int64($0,0))};guard count==expected else{throw Failure.identity}}
            var meta:[String:String]=[:];try Self.query(db,"SELECT key,value FROM metadata",[]){meta[try Self.text($0,0)]=try Self.text($0,1)}
            guard meta["kind"]=="vipi.source-candidate-catalog",meta["schema"]=="1",meta["permission"]=="disabled_research_only",meta["context_pack_sha256"]==contextPack.contentSHA256,meta["policy_sha256"]==m["contract_sha256"] as? String else{throw Failure.identity}
            for lang in ["en","es"] {for suffix in ["_sha256","_metadata_json"] {let k="dictionary_"+lang+suffix;guard meta[k]==contextPack.metadata[k] else{throw Failure.identity}}}
            guard try Self.digest(url,maximum:256<<20)==hash else{throw Failure.identity};metadata=meta
        } catch {sqlite3_close(db);throw error}
    }
    deinit {sqlite3_close(db)}
    private static func text(_ s:OpaquePointer,_ c:Int32)throws->String {guard sqlite3_column_type(s,c)==SQLITE_TEXT,sqlite3_column_bytes(s,c)<=262144,let p=sqlite3_column_text(s,c),let v=String(data:Data(bytes:p,count:Int(sqlite3_column_bytes(s,c))),encoding:.utf8) else{throw Failure.malformed};return v}
    private static func query(_ db:OpaquePointer,_ sql:String,_ values:[String],body:(OpaquePointer)throws->Void)throws {
        var p:OpaquePointer?;guard sqlite3_prepare_v2(db,sql,-1,&p,nil)==SQLITE_OK,let p else{throw Failure.sqlite};defer{sqlite3_finalize(p)}
        for (i,v) in values.enumerated(){guard sqlite3_bind_text(p,Int32(i+1),v,-1,unsafeBitCast(-1,to:sqlite3_destructor_type.self))==SQLITE_OK else{throw Failure.sqlite}}
        var count=0
        while true {let s=sqlite3_step(p);if s==SQLITE_DONE{break};guard s==SQLITE_ROW else{throw Failure.sqlite};count+=1;guard count<=2_000_000 else{throw Failure.bound};try body(p)}
    }
    func heads(sourceKey:String,ordinary:Bool)throws->[Head] {
        guard sourceKey.utf8.count<=4096 else{throw Failure.bound};var result:[Head]=[]
        try Self.query(db,"SELECT id,source_key,context_id,baseline,conditional,train_rank,record_json,audit_json,record_sha256,audit_sha256 FROM candidates WHERE source_key=? AND baseline=? ORDER BY id",[sourceKey,ordinary ? "1":"0"]){s in
            let raw=try Self.text(s,6),audit=try Self.text(s,7),id=try Self.text(s,0),key=try Self.text(s,1),cid=try Self.text(s,2)
            guard Self.hash(raw)==(try Self.text(s,8)),Self.hash(audit)==(try Self.text(s,9)),let record=try JSONSerialization.jsonObject(with:Data(raw.utf8)) as? [String:Any],let a=try JSONSerialization.jsonObject(with:Data(audit.utf8)) as? [String:Any],record["id"] as? String==id,record["source_key"] as? String==key,record["context_id"] as? String==cid else{throw Failure.identity}
            let baseline=Int(sqlite3_column_int(s,3)),conditional=Int(sqlite3_column_int(s,4)),rank=Int(sqlite3_column_int64(s,5));guard [0,1].contains(baseline),conditional==1-baseline,rank>=0 else{throw Failure.malformed}
            result.append(.init(id:id,key:key,contextID:cid,ordinary:baseline==1,conditional:conditional==1,rank:rank,recordJSON:raw,auditJSON:audit,record:record,audit:a));guard result.count<=65536 else{throw Failure.bound}
        };return result
    }
    func keys(headID:String)throws->[String] {var a:[String]=[];try Self.query(db,"SELECT source_key FROM head_keys WHERE head_id=? ORDER BY source_key",[headID]){a.append(try Self.text($0,0))};guard a.count<=256 else{throw Failure.bound};return a}
    /// Exact full evidence is available lazily, never loaded for unrelated heads.
    func evidence(headID:String)throws->[[String:String]] {var a:[[String:String]]=[];try Self.query(db,"SELECT h.kind,h.identity,h.evidence_id,e.value_json FROM head_evidence h JOIN evidence e ON e.id=h.evidence_id WHERE h.head_id=? ORDER BY h.kind,h.identity,h.evidence_id",[headID]){a.append(["kind":try Self.text($0,0),"identity":try Self.text($0,1),"evidence_id":try Self.text($0,2),"value_json":try Self.text($0,3)])};return a}
}
