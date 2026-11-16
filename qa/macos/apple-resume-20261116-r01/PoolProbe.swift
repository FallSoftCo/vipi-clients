import Foundation
import VipiCore
@main struct PoolProbe {
 @MainActor static func main() async throws {
  let out=URL(fileURLWithPath:CommandLine.arguments[1])
  let sourceWords=["one","two","three","four","five","six","seven"]
  let targets=["uno","dos","tres","cuatro","cinco","seis","siete"]
  let patterns:[[String:Any]]=zip(sourceWords,targets).map { word,target in
   ["id":"reviewed:test:"+word,"pair":"en-es","source":word,"target":target,"reading":"","meaning":"synthetic "+word,"concept_id":"test-"+word,"source_only_permission":true,"variants":[["context":word,"focus_utf16":[0,word.utf16.count]]]]
  }
  let pack:[String:Any]=["schema":"vipi-source-frame-pack-1","version":"001","source":"en","target":"es","policy":"reference-first-source-frames-1","approval_sha256":String(repeating:"a",count:64),"patterns":patterns]
  let bytes=try JSONSerialization.data(withJSONObject:pack,options:[.sortedKeys])
  let manifest:[String:Any]=["schema":"vipi-source-frame-manifest-1","file":"source-frames-en-es-001.json","sha256":JapaneseStarterLookup.digest(bytes),"version":"001","source":"en","target":"es","policy":"reference-first-source-frames-1","bytes":bytes.count,"patterns":patterns.count]
  let mb=try JSONSerialization.data(withJSONObject:manifest,options:[.sortedKeys])
  let baselineID="pool-test-baseline"
  let baseline=SourceUnitLookup(identity:baselineID) { c in .init(original:c.original,source:c.pair.source,target:c.pair.target,catalogIdentity:baselineID,partial:nil,recognitions:[]) }
  let owner=try SourceFrameLookup(bytes:bytes,manifestBytes:mb,target:"es",baselineIdentity:baselineID)
  let inner=owner.provider(baseline:baseline,raw:{[]})
  guard let composed=BundledStarterLookup.compose(japanese:nil,swahili:nil,candidates:["en-es":inner]) else { fatalError("dispatch") }
  let text="one two three four five six seven eight",pair=TranslationPair(source:"en",target:"es")
  let evidence=try await composed.resolve(.init(original:text,pair:pair,density:0.75,knownConceptIDs:[]))
  guard evidence.validated(text:text,sourceLanguage:"en",targetLanguage:"es",identity:composed.identity) != nil, let pool=evidence.eligiblePool,let n=evidence.nativeSourceTokenCount else { fatalError("invalid pool") }
  precondition(pool.count == 7 && evidence.partial?.references.count == 6)
  let history:[AdditiveReferenceSelection.History]=pool.map { $0.original == "seven" ? .seen(due:true) : .novel }
  let selected=AdditiveReferenceSelection.select(units:pool,history:history,nativeSourceTokenCount:n,density:0.25,preserveProducerPriority:true)!
  precondition(selected.count==3 && selected.contains(where:{$0.original=="seven"}) && selected.filter({$0.original != "seven"}).count==2)
  precondition(pool.allSatisfy { $0.reviewedFrameIdentity != nil })
  var actual:[[String:Any]]=[]
  if let provider=BundledStarterLookup.provider() {
   for target in ["ja","sw"] {
    let input="I heard music.", pair=TranslationPair(source:"en",target:target)
    let e=try await provider.resolve(.init(original:input,pair:pair,density:0.75,knownConceptIDs:[]))
    let p=e.eligiblePool ?? []
    let picked=AdditiveReferenceSelection.select(units:p,history:p.map{_ in .novel},nativeSourceTokenCount:e.nativeSourceTokenCount ?? 3,density:0.25,preserveProducerPriority:true) ?? []
    actual.append(["target":target,"input":input,"pool":p.map(\.original),"selected":picked.map(\.original),"hasPool":e.eligiblePool != nil])
   }
  }
  let result:[String:Any]=["scope":"native macOS direct provider; synthetic reviewed pack and existing bundled starter traces; no app UI", "synthetic_pool_count":pool.count,"old_capped_count":evidence.partial?.references.count ?? -1,"selected":selected.map(\.original),"actual_starter":actual]
  try JSONSerialization.data(withJSONObject:result,options:[.prettyPrinted,.sortedKeys]).write(to:out,options:.withoutOverwriting)
 }
}
