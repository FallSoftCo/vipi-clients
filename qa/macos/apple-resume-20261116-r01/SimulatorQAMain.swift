// Isolated simulator qualification entrypoint. Never included in production.
import SwiftUI
import CryptoKit
import AVFoundation
import VipiCore

@MainActor @Observable final class AdditiveSimulatorQA {
 let firstText="seven", secondText="one two three four five six seven eight"
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
   let words=["one","two","three","four","five","six","seven"], translations=["一","二","三","四","五","六","七"], readings=["ichi","ni","san","yon","go","roku","nana"]
   let patterns:[[String:Any]]=words.indices.map { i in
    ["id":"qa:frame:"+words[i],"pair":"en-ja","source":words[i],"target":translations[i],"reading":readings[i],"meaning":"synthetic "+words[i],"concept_id":"qa-"+words[i],"source_only_permission":true,"variants":[["context":words[i],"focus_utf16":[0,words[i].utf16.count]]]]
   }
   let pack:[String:Any]=["schema":"vipi-source-frame-pack-1","version":"001","source":"en","target":"ja","policy":"reference-first-source-frames-1","approval_sha256":String(repeating:"a",count:64),"patterns":patterns]
   let data=try JSONSerialization.data(withJSONObject:pack,options:[.sortedKeys]), hash=JapaneseStarterLookup.digest(data)
   let manifest:[String:Any]=["schema":"vipi-source-frame-manifest-1","file":"source-frames-en-ja-001.json","sha256":hash,"version":"001","source":"en","target":"ja","policy":"reference-first-source-frames-1","bytes":data.count,"patterns":patterns.count]
   let manifestData=try JSONSerialization.data(withJSONObject:manifest,options:[.sortedKeys]), baselineID="synthetic-ui-baseline"
   let baseline=SourceUnitLookup(identity:baselineID) { c in .init(original:c.original,source:c.pair.source,target:c.pair.target,catalogIdentity:baselineID,partial:nil,recognitions:[]) }
   let frames=try SourceFrameLookup(bytes:data,manifestBytes:manifestData,target:"ja",baselineIdentity:baselineID)
   let provider=frames.provider(baseline:baseline,raw:{[]})
   let dispatch=BundledStarterLookup.compose(japanese:provider,swahili:nil)!
   owner=ConversationImmersion(modelStatus:{_ in .unsupported},sourceUnits:dispatch)
  } catch { fatalError("synthetic QA setup failed: \(error)") }
 }
 func write(_ fields:[String:Any]) {
  var result=fields;result["scope"]="isolated simulator QA: synthetic hash-bound source frames and injected test-key vault; no auth or keychain";result["speech"]=speechResult
  if let data=try? JSONSerialization.data(withJSONObject:result,options:[.prettyPrinted,.sortedKeys]) { try? data.write(to:report,options:.atomic) }
 }
 func start() async {
  await owner.configure(pair:.init(source:"en",target:"ja"),density:0.25,familiarity:store)
  owner.selectInputLanguage("en",for:"qa-first");owner.selectInputLanguage("en",for:"qa-second")
  first=await owner.result(for:firstText,inputLanguage:"en",messageID:"qa-first")
  guard let first,first.spans.map(\.original)==["seven"] else { status="First selection failed";write(["stage":"first_failed"]);return }
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
   status=before.contains("seven") && before.count==3 ? "Waiting for second visible dwell" : "Selection mismatch"
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
   status=before.contains("seven") && before.count==3 && stable ? "PASS: seen plus new; stable" : "Selection mismatch"
   write(["stage":"second_dwell","first":first.spans.map(\.original),"second":before,"stable":stable,"readings":readings,"history_revision":store.frameHistoryRevision])
   do {
    let root=FileManager.default.urls(for:.cachesDirectory,in:.userDomainMask)[0].appendingPathComponent("qa-speech-"+UUID().uuidString)
    let pair=try LocalSpeechPair(source:"en",target:"ja",root:root)
    defer { pair.stop() }
    try await pair.prepare(warmups:["en":"hello","ja":"こんにちは"])
    let parts=second.speech(source:"en",target:"ja").map { (text:$0.text,language:$0.language) }
    let rendered=try await pair.render(parts)
    let file=try AVAudioFile(forReading:rendered.file)
    guard file.length > 0 else { throw LocalSpeechError.invalidAudio }
    speechResult="rendered actual selected words, \(file.length) frames"
   } catch { speechResult="failed: \(error)" }
   write(["stage":"complete","first":first.spans.map(\.original),"second":before,"stable":stable,"readings":readings,"history_revision":store.frameHistoryRevision])
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
       Text("Vipi additive QA").font(.title)
       Text(qa.status).accessibilityIdentifier("qa-status")
       if let first=qa.first {
        ImmersionBubble(result:first,mode:.immersed,speech:qa.speech,sourceLanguage:"en",targetLanguage:"ja",messageID:"qa-first",targetDwell:.milliseconds(500),meaningDwell:.seconds(3),onExposure:qa.exposedFirst)
       }
       if let second=qa.second {
        ImmersionBubble(result:second,mode:.immersed,speech:qa.speech,sourceLanguage:"en",targetLanguage:"ja",messageID:"qa-second",targetDwell:.milliseconds(500),meaningDwell:.seconds(3),onExposure:qa.exposedSecond)
       }
      }.padding()
     }.navigationTitle("Word switching")
    }.environment(state).task { await qa.start() }
   }
  }
 }
}
