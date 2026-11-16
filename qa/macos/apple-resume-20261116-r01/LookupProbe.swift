import Foundation
import VipiCore
@main struct LookupProbe {
 @MainActor static func main() async throws {
  let carrierChecks = try checkCarrierMetadata()
  let fixture=try JSONSerialization.jsonObject(with:Data(contentsOf:URL(fileURLWithPath:CommandLine.arguments[1]))) as! [String:Any]
  guard let lookup=BundledStarterLookup.provider() else {fatalError("No bundled provider")}
  var rows:[[String:Any]]=[]
  for input in fixture["cases"] as! [[String:Any]] {
   let source=input["source_language"] as! String,target=input["target_language"] as! String,text=input["original"] as! String
   var modes:[[String:Any]]=[]
   for density in [0.25,0.5] {
    let evidence=try await lookup.resolve(.init(original:text,pair:.init(source:source,target:target),density:density,knownConceptIDs:[]))
    let spans=evidence.partial?.spans ?? []
    modes.append(["density":density,"spans":spans.map{["source":$0.original,"target":$0.translated,"reading":$0.romanization as Any? ?? NSNull(),"start_utf16":$0.range.location,"length_utf16":$0.range.length] as [String:Any]}])
   }
   rows.append(["fixture":input,"direct":modes])
  }
  try JSONSerialization.data(withJSONObject:["carrier_metadata_checks":carrierChecks,"scope":"Exact bundled production source providers and native tokenizer; direct only, does not qualify automatic classification or ConversationImmersion", "rows":rows],options:[.sortedKeys]).write(to:URL(fileURLWithPath:CommandLine.arguments[2]),options:.withoutOverwriting)
 }
}
