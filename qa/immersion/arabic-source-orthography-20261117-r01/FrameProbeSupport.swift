import Foundation
import CryptoKit
import VipiCore
// Compile-only seams for unused app resource factories. No matching decision is
// stubbed: actual LocalImmersion, SourceUnitLookup and SourceFrameLookup compile.
struct TranslationPair: Sendable { let source:String,target:String }
enum JapaneseStarterLookup {
    static func digest(_ data:Data)->String { SHA256.hash(data:data).map{String(format:"%02x",$0)}.joined() }
}
final class BundledImmersionCatalog {
    func reference(original:String,pair:TranslationPair) async throws -> String? { fatalError("Unused resource-factory seam") }
}
@MainActor func makeFrame(context:String,head:String,start:Int,end:Int,carrier:Bool=false)->SourceFrameLookup {
    var variant:[String:Any]=["context":context,"focus_utf16":[start,end]]
    if carrier {variant["carrier_utf16"]=[0,context.utf16.count];variant["carrier_rule"]="supplied-singular-definite-article-1"}
    let pattern:[String:Any]=["id":"qa-frame","pair":"ar-en","source":head,"target":head.contains("موسيقى") ? "music":"water","reading":"","meaning":"explicit supplied fixture meaning","concept_id":"qa","source_only_permission":true,"variants":[variant]]
    let pack:[String:Any]=["schema":"vipi-source-frame-pack-1","source":"ar","target":"en","policy":"reference-first-source-frames-1","approval_sha256":String(repeating:"a",count:64),"version":"qa","patterns":[pattern]]
    let bytes=try! JSONSerialization.data(withJSONObject:pack,options:[.sortedKeys])
    let manifest:[String:Any]=["schema":"vipi-source-frame-manifest-1","file":"source-frames-ar-en-001.json","source":"ar","target":"en","policy":"reference-first-source-frames-1","version":"qa","sha256":JapaneseStarterLookup.digest(bytes),"bytes":bytes.count,"patterns":1]
    return try! SourceFrameLookup(bytes:bytes,manifestBytes:JSONSerialization.data(withJSONObject:manifest),target:"en",baselineIdentity:"empty",source:"ar")
}
