import Foundation
import VipiCore
@main struct Zero {
 @MainActor static func main() async throws {
  let p=BundledStarterLookup.provider()!,text="I like music."
  var rows=[[String:Any]]()
  for target in ["ja","sw"] {
   let pair=TranslationPair(source:"en",target:target)
   let off=try await p.resolve(.init(original:text,pair:pair,density:0,knownConceptIDs:[]))
   let on=try await p.resolve(.init(original:text,pair:pair,density:0.75,knownConceptIDs:[]))
   guard off.validated(text:text,sourceLanguage:"en",targetLanguage:target,identity:p.identity) != nil, off.partial == nil, off.eligiblePool == nil, let pool=on.eligiblePool, let count=on.nativeSourceTokenCount else {fatalError("off/provider")}
   let seen=pool.map{_ in AdditiveReferenceSelection.History.seen(due:true)}
   let mixed=pool.enumerated().map{ $0.offset == 0 ? AdditiveReferenceSelection.History.novel : .seen(due:true) }
   guard AdditiveReferenceSelection.select(units:pool,history:seen,nativeSourceTokenCount:count,density:0) == [], AdditiveReferenceSelection.select(units:pool,history:mixed,nativeSourceTokenCount:count,density:0) == [] else {fatalError("zero selection")}
   rows.append(["target":target,"offPartial":false,"offPool":false,"availablePositiveDensityUnits":pool.count,"zeroSeenAndMixedSelections":0])
  }
  try JSONSerialization.data(withJSONObject:rows,options:[.prettyPrinted,.sortedKeys]).write(to:URL(fileURLWithPath:CommandLine.arguments[1]))
 }
}
