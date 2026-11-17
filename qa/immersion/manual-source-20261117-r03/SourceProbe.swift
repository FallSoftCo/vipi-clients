import Foundation
@testable import VipiCore
@main struct SourceProbe {
 @MainActor static func main() async throws {
  let reverse=try await LookupFirst.resolve(.init(text:"Hola, amiga.",source:"en",target:"es",allowModelTranslation:false),valid:{true},reference:{_,from,_ in from=="es" ? "Hello, friend." : nil},identify:{_ in fatalError("authored reference detects direction")},modelsReady:{_,_ in fatalError("no model")},translate:{_,_,_ in fatalError("no model")},align:{a,b,_ in .init(original:a,translation:b,spans:[])})
  precondition(reverse.result?.original=="Hello, friend." && reverse.result?.translation=="Hola, amiga.")
  precondition(reverse.resolvedInputLanguage=="es" && reverse.cachedInvocation().resolvedInputLanguage=="es")
  let miss=try await LookupFirst.resolve(.init(text:"Una frase desconocida.",source:"en",target:"es",allowModelTranslation:false),valid:{true},reference:{_,_,_ in nil},identify:{_ in "es"},modelsReady:{_,_ in fatalError("no model")},translate:{_,_,_ in fatalError("no model")},align:{_,_,_ in fatalError("no alignment")})
  precondition(miss.status == .noLocalMatch && miss.result==nil && miss.resolvedInputLanguage=="es")
  var valid=true
  let stale=try await LookupFirst.resolve(.init(text:"Una frase.",source:"en",target:"es",inputLanguage:"es"),valid:{valid},reference:{_,_,_ in nil},identify:{_ in nil},modelsReady:{_,_ in valid=false;return false},translate:{_,_,_ in "x"},align:{a,b,_ in .init(original:a,translation:b,spans:[])})
  precondition(stale.status == .stale && stale.resolvedInputLanguage==nil)
  let invalid=try await LookupFirst.resolve(.init(text:"x",source:"en",target:"es",inputLanguage:"fr"),valid:{true},reference:{_,_,_ in fatalError("invalid before callbacks")},identify:{_ in nil},modelsReady:{_,_ in false},translate:{_,_,_ in "x"},align:{a,b,_ in .init(original:a,translation:b,spans:[])})
  precondition(invalid.resolvedInputLanguage==nil)
  let raw="Hola, amiga."
  let mismatch=ManualSourceCoordinates.resolve(rawOriginal:raw,displayedSource:reverse.result!.original,startUTF16:7,endUTF16:13)!
  precondition(mismatch.startUTF16==0 && mismatch.endUTF16==raw.utf16.count && mismatch.expanded)
  let direct=ManualSourceCoordinates.resolve(rawOriginal:raw,displayedSource:raw,startUTF16:6,endUTF16:11)!
  precondition(direct.startUTF16==6 && direct.endUTF16==11 && !direct.expanded)
  let nfd="cafe\u{301}"
  precondition(ManualSourceCoordinates.resolve(rawOriginal:nfd,displayedSource:"café",startUTF16:0,endUTF16:4)!.expanded)
  for (text,a,b) in [("A😀B",2,3),(nfd,0,4),("Hola.",-1,2),("Hola.",0,99)] {
   let r=ManualSourceCoordinates.resolve(rawOriginal:text,displayedSource:text,startUTF16:a,endUTF16:b)!
   precondition(r.startUTF16==0 && r.endUTF16==text.utf16.count && r.expanded)
  }
  precondition(ManualSourceCoordinates.resolve(rawOriginal:"",displayedSource:"Hello",startUTF16:0,endUTF16:5)==nil)
  let request=ManualTranslationRequest(messageID:"reverse",originalText:raw,startUTF16:mismatch.startUTF16,endUTF16:mismatch.endUTF16,knownLanguage:"en",learningLanguage:"es",inputLanguage:reverse.resolvedInputLanguage,generation:1,ownerGeneration:UUID())
  var actualInput="",direction=""
  let translated=try await ManualTranslationResolver.resolve(request,valid:{true},reference:{_,_,_ in nil},identify:{_ in fatalError("direction retained")},modelsReady:{_,_ in true},translate:{text,a,b in actualInput=text;direction=a+"-"+b;return "Hello, friend."},reading:{_,_ in nil})
  precondition(translated.status == .ready && actualInput==raw && direction=="es-en")
  let report:[String:Any]=["passed":true,"scope":"native macOS production core/helper with injected translation; not mobile UI or model quality","checks":["reverse authored normalization retained","resolved actual language cached","target-language no-match metadata","stale and prevalidation metadata cleared","mismatched normalized source maps whole raw","exact raw preserves selection","NFC/NFD exact-byte distinction","surrogate/combining/invalid offsets fall back whole raw","invalid empty raw rejected","reverse manual input and direction exact"]]
  try JSONSerialization.data(withJSONObject:report,options:[.prettyPrinted,.sortedKeys]).write(to:URL(fileURLWithPath:CommandLine.arguments[1]))
  print("Passed source-coordinate and actual-language regressions")
 }
}
