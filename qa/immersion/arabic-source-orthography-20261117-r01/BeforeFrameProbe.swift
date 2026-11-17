import Foundation
import VipiCore
@main struct BeforeFrameProbe {
 @MainActor static func main() throws {
  var rows:[[String:Any]]=[]
  for(text,head) in [("أنا أشرب الماء الآن.","ماء"),("أنا أحب الموسيقى.","موسيقى")] {
   let frame=makeFrame(context:head,head:head,start:0,end:head.utf16.count)
   let baseline=SourceLookupEvidence(original:text,source:"ar",target:"en",catalogIdentity:"empty",partial:nil,recognitions:[])
   let result=try frame.resolve(original:text,density:0.5,known:[],baseline:baseline,raw:[])
   let word="ال"+head
   let carrierFrame=makeFrame(context:word,head:head,start:2,end:word.utf16.count,carrier:true)
   let carrierResult=try carrierFrame.resolve(original:text,density:0.5,known:[],baseline:baseline,raw:[])
   precondition(carrierResult.partial?.spans.map(\.original)==[head])
   let focus=(text as NSString).range(of:head)
   let entry=VocabularyEntry(source:head,targets:[head=="ماء" ? "water":"music"],sourceScope:.init(original:text,start:focus.location,end:NSMaxRange(focus)))
   let scoped=ImmersionEngine().align(original:text,translation:head=="ماء" ? "water":"music",entries:[entry],density:1,targetLanguage:"en",sourceTokenCount:8)
   precondition(scoped.spans.map(\.original)==[head])
   rows.append(["text":text,"nativeWordRanges":LocalImmersion.words(text,language:"ar").map{[$0.location,NSMaxRange($0)]},"ordinaryBareGeometry":try frame.geometry(text),"ordinaryBareAdmittedSourceFaces":result.partial?.spans.map(\.original) ?? [],"carrierGeometry":try carrierFrame.geometry(text),"carrierAdmittedSourceFaces":carrierResult.partial!.spans.map(\.original),"coreScopedSourceRanges":scoped.spans.map{[$0.range.location,NSMaxRange($0.range)]}])
  }
  try JSONSerialization.data(withJSONObject:["scope":"unchanged pre-fix production matcher and existing old core library; native tokenizer","cases":rows],options:[.prettyPrinted,.sortedKeys,.withoutEscapingSlashes]).write(to:URL(fileURLWithPath:CommandLine.arguments[1]))
 }
}
