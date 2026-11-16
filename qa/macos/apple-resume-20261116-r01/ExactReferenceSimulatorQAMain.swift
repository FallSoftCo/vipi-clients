// Isolated simulator qualification entrypoint. Never included in production.
import SwiftUI
import CryptoKit
import AVFoundation
import VipiCore

@MainActor @Observable final class AdditiveSimulatorQA {
 let firstText="I", secondText="I like music."
 let store:VocabularyFamiliarityStore
 let owner:ConversationImmersion
 let speech=SpeechPlayback()
 var first:ImmersionPresentation?
 var second:ImmersionPresentation?
 var status="Preparing local test"
 var advanced=false
 var secondObserved=false
 var speechResult="not attempted"
 let report=FileManager.default.urls(for:.documentDirectory,in:.userDomainMask)[0].appendingPathComponent("additive-qa-receipt.json")
 init() {
  do {
   let root=FileManager.default.urls(for:.documentDirectory,in:.userDomainMask)[0].appendingPathComponent("synthetic-vault-"+UUID().uuidString)
   let vault=try MessageVault(account:UUID(),directory:root,testKey:SymmetricKey(data:Data((0..<32).map(UInt8.init))))
   store=VocabularyFamiliarityStore(vault:vault)
   guard let dispatch=SwahiliStarterLookup.bundledIfPromoted() else { fatalError("missing bundled Swahili starter") }
   owner=ConversationImmersion(modelStatus:{_ in .unsupported},sourceUnits:dispatch)
  } catch { fatalError("synthetic QA setup failed: \(error)") }
 }
 func write(_ fields:[String:Any]) {
  var result=fields;result["scope"]="isolated simulator QA: actual bundled Swahili starter and frame packs on a forward exact reference with injected test-key vault; no auth or keychain";result["speech"]=speechResult
  if let data=try? JSONSerialization.data(withJSONObject:result,options:[.prettyPrinted,.sortedKeys]) { try? data.write(to:report,options:.atomic) }
 }
 func start() async {
  speech.prepare(source:"en",target:"sw",warmups:["en":"hello","sw":"habari"])
  await owner.configure(pair:.init(source:"en",target:"sw"),density:0.25,familiarity:store)
  owner.selectInputLanguage("en",for:"qa-first");owner.selectInputLanguage("en",for:"qa-second")
  first=await owner.result(for:firstText,inputLanguage:"en",messageID:"qa-first")
  guard let first,first.spans.map(\.original)==["I"] else { status="First selection failed";write(["stage":"first_failed"]);return }
  status="Waiting for visible word dwell";write(["stage":"first_visible","first":first.spans.map(\.original)])
 }
 func exposedFirst(_ spans:[ImmersionSpan]) {
  guard !advanced,let first else { return };advanced=true
  let identity=owner.identity(messageID:"qa-first",text:firstText)
  owner.observeExposure(spans,presentation:first,identity:identity)
  Task { @MainActor in
   second=await owner.result(for:secondText,inputLanguage:"en",messageID:"qa-second")
   guard let second else { status="Second selection failed";write(["stage":"second_failed"]);return }
   let before=second.spans.map(\.original)
   status=before == ["music"] ? "Waiting for second visible dwell" : "Selection mismatch"
   write(["stage":"second_visible","first":first.spans.map(\.original),"second":before])
  }
 }
 func exposedSecond(_ spans:[ImmersionSpan]) {
  guard !secondObserved,let second,let first else { return };secondObserved=true
  let before=second.spans.map(\.original), id=owner.identity(messageID:"qa-second",text:secondText)
  owner.observeExposure(spans,presentation:second,identity:id)
  Task { @MainActor in
   let again=await owner.result(for:secondText,inputLanguage:"en",messageID:"qa-second")
   let stable=again == second
   let readings=second.spans.map { ["source":$0.original,"target":$0.translated,"reading":$0.romanization ?? ""] }
   status=before == ["music"] && stable ? "PASS: seen plus new; stable" : "Selection mismatch"
   write(["stage":"second_dwell","first":first.spans.map(\.original),"second":before,"stable":stable,"readings":readings,"frame_history_revision":store.frameHistoryRevision,"starter_history_revision":store.starterHistoryRevision])
   for _ in 0..<100 {
    if speech.state == .ready || speech.state == .unavailable { break }
    try? await Task.sleep(for:.milliseconds(100))
   }
   if speech.state == .ready {
    let parts=second.speech(source:"en",target:"sw").map { (text:$0.text,language:$0.language) }
    speech.toggle(message:"qa-second",spans:parts)
    var playing=false
    for _ in 0..<300 {
     if speech.state == .playing { playing=true }
     if playing && speech.state == .ready { break }
     if speech.error != nil { break }
     try? await Task.sleep(for:.milliseconds(100))
    }
    speechResult="controller playing=\(playing), state=\(speech.state), underruns=\(speech.outputUnderruns), error=\(speech.error ?? "none")"
   } else { speechResult="prepare failed: \(speech.error ?? "timeout")" }
   write(["stage":"complete","first":first.spans.map(\.original),"second":before,"stable":stable,"readings":readings,"frame_history_revision":store.frameHistoryRevision,"starter_history_revision":store.starterHistoryRevision])
  }
 }
}

@main struct VipiApp: App {
 @State private var qa=AdditiveSimulatorQA()
 @State private var state=AppState()
 var body: some Scene {
  WindowGroup {
   if ProcessInfo.processInfo.arguments.contains("-qa-settings") {
    NavigationStack { SettingsView() }.environment(state).dynamicTypeSize(.accessibility3)
   } else {
    NavigationStack {
     ScrollView {
      VStack(alignment:.leading,spacing:20) {
       Text("Vipi starter QA").font(.title)
       Text(qa.status).accessibilityIdentifier("qa-status")
       if let first=qa.first {
        ImmersionBubble(result:first,mode:.immersed,speech:qa.speech,sourceLanguage:"en",targetLanguage:"sw",messageID:"qa-first",targetDwell:.milliseconds(500),meaningDwell:.seconds(3),onExposure:qa.exposedFirst)
       }
       if let second=qa.second {
        ImmersionBubble(result:second,mode:.immersed,speech:qa.speech,sourceLanguage:"en",targetLanguage:"sw",messageID:"qa-second",targetDwell:.milliseconds(500),meaningDwell:.seconds(3),onExposure:qa.exposedSecond)
       }
      }.padding()
     }.navigationTitle("Word switching")
    }.environment(state).task { await qa.start() }
   }
  }
 }
}
