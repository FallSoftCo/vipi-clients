// Isolated simulator speech qualification; never included in product.
import SwiftUI
import AVFoundation
@MainActor @Observable final class SpeechMatrixQA {
 let words = ["en":"water", "es":"agua", "fr":"eau", "de":"Wasser", "it":"acqua", "pt":"água", "ar":"ماء", "zh":"水", "ja":"水", "ko":"물", "sw":"maji"]
 let excluded = ["en-ja":"r54: completed UI playback", "en-sw":"r61/r68: completed controller playback"]
 let path=FileManager.default.urls(for:.documentDirectory,in:.userDomainMask)[0].appendingPathComponent("speech-matrix.json")
 var status="Preparing";var rows=[[String:Any]]()
 func save(_ stage:String,_ current:String="") {
  let result:[String:Any] = ["stage":stage,"current":current,"scope":"iOS Simulator synthetic two-word mixed output; no listening or pronunciation assessment; no auth or keychain", "excludedPriorCompletion":excluded,"rows":rows]
  if let data=try? JSONSerialization.data(withJSONObject:result,options:[.prettyPrinted,.sortedKeys]) { try? data.write(to:path,options:.atomic) }
 }
 func run() async {
  let languages=words.keys.sorted();save("running")
  for source in languages { for target in languages where source != target {
   let pair=source+"-"+target
   if excluded[pair] != nil { continue }
   status="Testing "+pair;save("running",pair)
   let player=SpeechPlayback();let start=Date();var row:[String:Any]=["pair":pair,"source":source,"target":target,"sourceText":words[source]!,"targetText":words[target]!]
   do {
    let left=try? LocalVoice(language:source), right=try? LocalVoice(language:target)
    row["sourceVoice"]=left?.identifier ?? "unavailable";row["targetVoice"]=right?.identifier ?? "unavailable"
    row["sourceEngine"]=source == "sw" ? "bundled eSpeak" : "system AVSpeechSynthesizer"
    row["targetEngine"]=target == "sw" ? "bundled eSpeak" : "system AVSpeechSynthesizer"
    left?.stop();right?.stop()
    player.prepare(source:source,target:target,warmups:[source:words[source]!,target:words[target]!])
    for _ in 0..<300 { if player.state == .ready || player.state == .unavailable {break}; try? await Task.sleep(for:.milliseconds(50)) }
    if player.state == .ready {
     player.toggle(message:pair,spans:[(text:words[source]!,language:source),(text:words[target]!,language:target)])
     var playing=false
     for _ in 0..<400 {
      if player.state == .playing && player.activeMessage == pair { playing=true }
      if player.error != nil || (playing && player.state == .ready) {break}
      try? await Task.sleep(for:.milliseconds(50))
     }
     row["sawPlaying"]=playing;row["finalState"]=String(describing:player.state);row["underruns"]=player.outputUnderruns;row["error"]=player.error ?? ""
     row["status"]=(playing && player.state == .ready && player.error == nil) ? "completed" : "playback_failed_or_timed_out"
    } else {row["status"]="prepare_failed_or_timed_out";row["error"]=player.error ?? "timeout";row["finalState"]=String(describing:player.state)}
   }
   row["elapsedMs"]=Int(Date().timeIntervalSince(start)*1000);player.close();rows.append(row);save("running")
  }}
  status="Finished";save("complete")
 }
}
@main struct VipiApp: App {
 @State private var qa=SpeechMatrixQA()
 var body:some Scene { WindowGroup { VStack { Text("Speech playback qualification");Text(qa.status) }.task { await qa.run() } } }
}
