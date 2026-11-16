// Independent simulator playback control qualification; no authentication or keychain.
import SwiftUI
import VipiCore
@MainActor @Observable final class SpeechControlQA {
 let speech=SpeechPlayback()
 var sawPlaying=false
 var status="Preparing voices"
 let receipt=FileManager.default.urls(for:.documentDirectory,in:.userDomainMask)[0].appendingPathComponent("speech-control-qa.json")
 let result:ImmersionPresentation
 init() {
  let original="one two three four five six seven eight"
  let units:[SourceReferenceUnit]=[
   .init(range:NSRange(location:8,length:5),original:"three",translated:"三",reading:"san",referenceID:"qa-three",catalogSHA256:String(repeating:"a",count:64),nativeSourceTokens:1),
   .init(range:NSRange(location:14,length:4),original:"four",translated:"四",reading:"yon",referenceID:"qa-four",catalogSHA256:String(repeating:"a",count:64),nativeSourceTokens:1),
   .init(range:NSRange(location:28,length:5),original:"seven",translated:"七",reading:"nana",referenceID:"qa-seven",catalogSHA256:String(repeating:"a",count:64),nativeSourceTokens:1)]
  result = .partial(SourceReferencePresentation.create(original:original,target:"ja",units:units,density:1,nativeSourceTokenCount:8)!)
 }
 func prepare() { speech.prepare(source:"en",target:"ja",warmups:["en":"hello","ja":"こんにちは"]) }
 func record() {
  if speech.state == .playing && speech.activeMessage == "qa-second" { sawPlaying=true }
  if speech.state == .ready { status=sawPlaying ? "Playback completed" : "Ready: tap Listen" }
  if speech.state == .playing { status="Playing the mixed message" }
  if speech.state == .unavailable { status=speech.error ?? "Voice unavailable" }
  let rows=result.spans.map { ["source":$0.original,"target":$0.translated,"reading":$0.romanization ?? ""] }
  let obj:[String:Any]=["scope":"independent iOS Simulator UI; actual product ImmersionBubble and SpeechPlayback; synthetic reviewed spans; Swahili stub unused", "state":String(describing:speech.state),"sawPlaying":sawPlaying,"activeMessage":speech.activeMessage ?? "", "error":speech.error ?? "", "underruns":speech.outputUnderruns,"spans":rows]
  if let data=try? JSONSerialization.data(withJSONObject:obj,options:[.prettyPrinted,.sortedKeys]) { try? data.write(to:receipt,options:.atomic) }
 }
}
@main struct SpeechControlApp: App {
 @State private var qa=SpeechControlQA()
 var body:some Scene {
  WindowGroup {
   NavigationStack {
    ScrollView {
     VStack(alignment:.leading,spacing:20) {
      Text("Playback control QA").font(.title)
      Text(qa.status).accessibilityIdentifier("qa-playback-status")
      ImmersionBubble(result:qa.result,mode:.immersed,speech:qa.speech,sourceLanguage:"en",targetLanguage:"ja",messageID:"qa-second",targetDwell:.seconds(120),meaningDwell:.seconds(3))
     }.padding()
    }.navigationTitle("Word switching")
   }.onAppear { qa.prepare();qa.record() }
    .onChange(of:qa.speech.state) { _,_ in qa.record() }
  }
 }
}
