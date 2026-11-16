import Foundation
import VipiCore
@main struct StarterPoolProbe {
 @MainActor static func main() async throws {
  let vectorCount=try checkStarterIdentities(CommandLine.arguments[2]);precondition(vectorCount==13)
  guard let provider=BundledStarterLookup.provider() else { fatalError("provider") }
  var rows:[[String:Any]]=[]
  for target in ["ja","sw"] {
   for text in ["I heard music.","i heard music.","I have hair."] {
    let pair=TranslationPair(source:"en",target:target)
    let evidence=try await provider.resolve(.init(original:text,pair:pair,density:0.75,knownConceptIDs:[]))
    guard evidence.validated(text:text,sourceLanguage:"en",targetLanguage:target,identity:provider.identity) != nil else { fatalError("evidence") }
    let pool=evidence.eligiblePool ?? []
    let items:[[String:Any]]=pool.map { u in
     ["source":u.original,"target":u.translated,"reference":u.referenceID,"starter":u.reviewedStarterIdentity?.entryID as Any? ?? NSNull(),"starter_key":u.reviewedStarterIdentity?.encoded.map{String(format:"%02x",$0)}.joined() as Any? ?? NSNull(),"frame":u.reviewedFrameIdentity?.patternID as Any? ?? NSNull()]
    }
    if target == "sw" && text.contains("hair") { precondition(!pool.contains { $0.reviewedStarterIdentity?.canonicalSource == "hair" }) }
    rows.append(["target":target,"text":text,"items":items])
   }
  }
  let output:[String:Any]=["scope":"native macOS, actual bundled starter provider and guard; no app UI", "starter_identity_vectors":vectorCount,"rows":rows]
  try JSONSerialization.data(withJSONObject:output,options:[.prettyPrinted,.sortedKeys]).write(to:URL(fileURLWithPath:CommandLine.arguments[1]),options:.withoutOverwriting)
 }
}
