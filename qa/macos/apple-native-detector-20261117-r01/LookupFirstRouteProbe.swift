import Foundation
import VipiCore
@main struct CandidateRoutes {
 @MainActor static func main() async throws {
  guard let provider=BundledStarterLookup.provider() else { fatalError("starter resources missing") }
  let catalog=BundledImmersionCatalog(),detector=MessageLanguage()
  var records:[[String:Any]]=[],failures:[String]=[]
  for target in ["ja","sw"] {
   for text in ["I love music.","I heard music.","I like music."] {
    var detectCalls=0,models=0,translates=0,aligns=0
    let result=try await LookupFirst.resolve(.init(text:text,source:"en",target:target,intent:.automaticImmersion,allowModelTranslation:false),valid:{true},reference:{t,s,d in try await catalog.reference(original:t,pair:.init(source:s,target:d))},identify:{ t in detectCalls += 1;return try await detector.identify(t,automatic:true)},modelsReady:{_,_ in models += 1;return false},translate:{_,_,_ in translates += 1;throw NSError(domain:"unexpected_translate",code:1)},align:{_,_,_ in aligns += 1;throw NSError(domain:"unexpected_align",code:1)},sourceEvidenceIdentity:provider.identity,sourceEvidence:{t,s,d in try await provider.resolve(.init(original:t,pair:.init(source:s,target:d),density:0.25,knownConceptIDs:[]))})
    let spans=result.result?.spans ?? [];let music=spans.first(where:{$0.original.lowercased()=="music"});let expected=target=="ja" ? "音楽" : "muziki";let ok=music?.translated==expected && translates==0 && models==0 && aligns==0 && (text=="I like music." ? detectCalls==0 : detectCalls==1)
    if !ok {failures.append(target+":"+text)}
    records.append(["target":target,"text":text,"status":result.status.rawValue,"spans":spans.map{["source":$0.original,"target":$0.translated,"reading":$0.romanization as Any? ?? NSNull()]},"identify_calls":detectCalls,"model_readiness_calls":models,"translation_calls":translates,"alignment_calls":aligns,"pass":ok])
   }
   var detectCalls=0
   let manual=try await LookupFirst.resolve(.init(text:"music",source:"en",target:target,inputLanguage:"en",intent:.automaticImmersion,allowModelTranslation:false),valid:{true},reference:{_,_,_ in nil},identify:{t in detectCalls += 1;return try await detector.identify(t,automatic:true)},modelsReady:{_,_ in false},translate:{_,_,_ in throw NSError(domain:"unexpected",code:1)},align:{_,_,_ in throw NSError(domain:"unexpected",code:1)},sourceEvidenceIdentity:provider.identity,sourceEvidence:{t,s,d in try await provider.resolve(.init(original:t,pair:.init(source:s,target:d),density:0.25,knownConceptIDs:[]))})
   let ok=detectCalls==0 && manual.result?.spans.first?.translated == (target=="ja" ? "音楽" : "muziki");if !ok{failures.append(target+":manual")};records.append(["target":target,"text":"music","override":"en","identify_calls":detectCalls,"status":manual.status.rawValue,"pass":ok])
  }
  let data=try JSONSerialization.data(withJSONObject:["scope":"macOS LookupFirst plus actual bundled starter/frame providers, exact wrapper, full r14 resource data, no model callback; source fixture not population estimate","rows":records,"failures":failures],options:[.prettyPrinted,.sortedKeys]);try data.write(to:URL(fileURLWithPath:CommandLine.arguments[1]),options:.withoutOverwriting);print("routes=\(records.count) failures=\(failures)");if !failures.isEmpty{exit(1)}
 }
}
