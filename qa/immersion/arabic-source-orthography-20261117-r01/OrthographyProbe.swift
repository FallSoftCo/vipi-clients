import Foundation
@testable import VipiCore
@main struct OrthographyProbe {
 @MainActor static func main() throws {
  let data=try Data(contentsOf:URL(fileURLWithPath:CommandLine.arguments[1]))
  let cases=(try JSONSerialization.jsonObject(with:data) as! [String:Any])["cases"] as! [[String:Any]]
  var rows:[[String:Any]]=[]
  for c in cases {
   let text=c["text"] as! String,a=c["startUTF16"] as! Int,b=c["endUTF16"] as! Int
   let allowed=SourceOrthography.permitsReplacement(in:text,range:.init(location:a,length:b-a))
   precondition(allowed==c["allowed"] as! Bool,"\(c["id"]!)")
   rows.append(["id":c["id"]!,"allowed":allowed])
  }
  func checkRange(_ text:String,_ a:Int,_ b:Int,_ target:String,_ allowed:Bool) {
   let range=NSRange(location:a,length:b-a),surface=(text as NSString).substring(with:range)
   for scoped in [false,true] {
    let entry=VocabularyEntry(source:surface,targets:[target],sourceScope:scoped ? .init(original:text,start:a,end:b):nil)
    let result=ImmersionEngine().align(original:text,translation:target,entries:[entry],density:1,targetLanguage:"en",sourceBoundaries:[a,b],sourceTokenCount:8)
    precondition(!result.spans.isEmpty==allowed,"core source admission \(surface) scoped=\(scoped)")
   }
   let unit=SourceReferenceUnit(range:range,original:surface,translated:target,reading:nil,referenceID:"qa",catalogSHA256:String(repeating:"a",count:64),nativeSourceTokens:1)
   let partial=SourceReferencePresentation.create(original:text,target:"en",units:[unit],density:1,nativeSourceTokenCount:8)
   precondition((partial != nil)==allowed)
   if let partial {precondition(ImmersionPresentation.partial(partial).speech(source:"ar",target:"en",revealed:Set(partial.spans.map(\.id))).map(\.text).joined().utf8.elementsEqual(text.utf8))}
  }
  checkRange("أنا أشرب الماء الآن.",11,14,"water",false)
  checkRange("أنا أشرب الماء الآن.",9,14,"water",true)
  checkRange("أنا أحب الموسيقى.",10,16,"music",false)
  checkRange("أنا أحب الموسيقى.",8,16,"music",true)
  let mixed="الماء كتاب",sha=String(repeating:"a",count:64)
  let units=[SourceReferenceUnit(range:.init(location:2,length:3),original:"ماء",translated:"water",reading:nil,referenceID:"bad",catalogSHA256:sha,nativeSourceTokens:1),SourceReferenceUnit(range:.init(location:6,length:4),original:"كتاب",translated:"book",reading:nil,referenceID:"good",catalogSHA256:sha,nativeSourceTokens:1)]
  let safe=SourceReferencePresentation.create(original:mixed,target:"en",units:units,density:1,nativeSourceTokenCount:2)!
  precondition(safe.spans.map(\.original)==["كتاب"])
  var frameRows:[[String:Any]]=[]
  for (text,head) in [("أنا أشرب الماء الآن.","ماء"),("أنا أحب الموسيقى.","موسيقى")] {
   let frame=makeFrame(context:head,head:head,start:0,end:head.utf16.count)
   let baseline=SourceLookupEvidence(original:text,source:"ar",target:"en",catalogIdentity:"empty",partial:nil,recognitions:[])
   let outcome=try frame.resolve(original:text,density:0.5,known:[],baseline:baseline,raw:[])
   precondition(outcome.partial==nil&&outcome.recognitions.isEmpty)
   let geometry=try frame.geometry(text)
   precondition(geometry.allSatisfy{$0["reason"] as? String=="partial_arabic_word"})
   frameRows.append(["text":text,"geometry":geometry,"nativeWordRanges":LocalImmersion.words(text,language:"ar").map{[$0.location,NSMaxRange($0)]}])
  }
  for (word,head) in [("الماء","ماء"),("الموسيقى","موسيقى")] {
   let frame=makeFrame(context:word,head:head,start:2,end:word.utf16.count,carrier:true)
   let geometry=try frame.geometry(word)
   precondition(geometry.first!["reason"] as? String=="partial_arabic_word")
  }
  let fullText="أنا أشرب الماء الآن"
  let fullFrame=makeFrame(context:fullText,head:"الماء",start:9,end:14)
  let fullBaseline=SourceLookupEvidence(original:fullText,source:"ar",target:"en",catalogIdentity:"empty",partial:nil,recognitions:[])
  let fullResult=try fullFrame.resolve(original:fullText,density:0.75,known:[],baseline:fullBaseline,raw:[])
  precondition(fullResult.partial?.spans.map(\.original)==["الماء"])
  precondition(!SourceOrthography.permitsReplacement(in:"😀ماء",range:.init(location:1,length:1)))
  let report:[String:Any]=["passed":true,"scope":"actual native macOS core, LocalImmersion NLTokenizer and SourceFrameLookup; no UI/model quality claim","cases":rows,"ordinary_and_scoped_admission":true,"mixed_safe_unit_retained":true,"actual_frame_paths":frameRows,"explicit_carrier_rejected":true,"full_token_frame_admitted":true]
  try JSONSerialization.data(withJSONObject:report,options:[.prettyPrinted,.sortedKeys,.withoutEscapingSlashes]).write(to:URL(fileURLWithPath:CommandLine.arguments[2]))
  print("Passed \(cases.count) source boundary fixtures, core admission and actual native frame regressions")
 }
}
