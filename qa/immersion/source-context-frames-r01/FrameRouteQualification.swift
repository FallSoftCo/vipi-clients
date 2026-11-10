#if DEBUG
import SwiftUI
import VipiCore

/// Isolated original-message host. Targets and spans come from the reviewed private reference-first provider; no supplied span.
@MainActor struct FrameRouteQualificationView: View {
    @State private var owner: ConversationImmersion
    private let providerIdentity: String
    private let setupFailure: String?
    init() {
        let target=ProcessInfo.processInfo.arguments.contains("-vipi-starter-sw") ? "sw" : "ja"
        do {
            guard let path=ProcessInfo.processInfo.environment["VIPI_FRAME_UI_INPUTS"] else { throw FrameContextAdapter.Invalid.evidence }
            let root=URL(fileURLWithPath:path)
            func read(_ name:String)throws->Data {try Data(contentsOf:root.appendingPathComponent(name))}
            let manifest=try JSONSerialization.jsonObject(with:read("manifest.json")) as! [String:Any]
            guard JapaneseStarterLookup.digest(try read("manifest.json"))=="7ebbcfdb1e72290a5fdd1beda5c9c99c1fda1940a92fc1152876e89880cc7896" else {throw FrameContextAdapter.Invalid.evidence}
            for (name,hash) in manifest["files"] as! [String:String] {guard JapaneseStarterLookup.digest(try read(name))==hash else {throw FrameContextAdapter.Invalid.evidence}}
            let spec=(manifest["packs"] as! [String:[String:String]])[target]!
            let baseline:SourceUnitLookup,raw:()->[FrameStarterCandidate]
            if target=="ja" {
                let x=try JapaneseStarterLookup(data:read(spec["pack"]!),manifest:read(spec["manifest"]!),packMultiple:true)
                baseline=x.provider();raw={x.rawCandidates}
            } else {
                let x=try SwahiliStarterLookup(data:read(spec["pack"]!),manifest:read(spec["manifest"]!),packMultiple:true)
                baseline=x.provider();raw={x.rawCandidates}
            }
            let adapter=try FrameContextAdapter(bytes:read(spec["patterns"]!),permissionBytes:read("permission-proposal.json"),target:target,baselineIdentity:baseline.identity)
            let identity=adapter.identity+":reference-first-v1",catalog=BundledImmersionCatalog()
            let provider=SourceUnitLookup(identity:identity) { context in
                let b=try await baseline.resolve(context)
                let reference=try await catalog.reference(original:context.original,pair:context.pair)
                let value:SourceLookupEvidence
                if reference != nil {value=b} else {value=try adapter.resolve(original:context.original,density:context.density,known:context.knownConceptIDs,baseline:b,raw:raw())}
                return SourceLookupEvidence(original:value.original,source:value.source,target:value.target,catalogIdentity:identity,partial:value.partial,recognitions:value.recognitions)
            }
            _owner=State(initialValue:ConversationImmersion(modelStatus:{_ in .unsupported},sourceUnits:provider));providerIdentity=identity;setupFailure=nil
        } catch {
            _owner=State(initialValue:ConversationImmersion(modelStatus:{_ in .unsupported},sourceUnits:nil));providerIdentity="failed";setupFailure=String(describing:error)
        }
    }
    @State private var speech = SpeechPlayback()
    @State private var ready = false
    @State private var proof = "pending"
    @State private var speechEvents = [String]()
    private var packed: Bool { ProcessInfo.processInfo.arguments.contains("-vipi-starter-packed") }
    private var expanded: Bool { ProcessInfo.processInfo.arguments.contains("-vipi-starter-expanded") }
    private var original: String { "We need a phone charger and your phone number." }
    private var density: Double { 0.75 }
    private var target: String { ProcessInfo.processInfo.arguments.contains("-vipi-starter-sw") ? "sw" : "ja" }
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment:.leading,spacing:16) {
                    Text("Private source-context chat qualification").font(.footnote)
                    if ready {
                        ConversationImmersionText(text:original,id:"frame-ui-"+target,immersion:owner,speech:speech,
                            paused:false,metadata:AnyView(Text("Owned local message")),onVoiceHelp:{})
                    }
                    Text(proof).font(.caption).accessibilityIdentifier("frame-route-proof")
                    Text(String(describing:speech.state)).font(.caption).accessibilityIdentifier("frame-route-speech-state")
                    Text(speechEvents.joined(separator:"|")).font(.caption).accessibilityIdentifier("frame-route-speech-events")
                }.padding()
            }.navigationTitle(target == "sw" ? "Swahili source route" : "Japanese source route")
        }
        .task {
            if let setupFailure { proof="failed:"+setupFailure;return }
            let id = "frame-ui-"+target
            await owner.configure(pair:.init(source:"en",target:target),density:density,knownConceptIDs:[])
            owner.selectInputLanguage("en",for:id)
            _ = await owner.result(for:original,inputLanguage:"en",messageID:id)
            guard let outcome=owner.lastOutcome,let result=outcome.result else { proof="failed:no result";return }
            let segments=result.speech(source:"en",target:target).map { ["text":$0.text,"language":$0.language] }
            let rows=result.spans.map { ["source":$0.original,"target":$0.translated,"reading":$0.romanization as Any? ?? NSNull(),"scope":[$0.range.location,NSMaxRange($0.range)]] as [String:Any] }
            let evidence:[String:Any] = ["original":original,"target":target,"density":density,"known_ids":[String](),
                "provider_identity":providerIdentity,"origin":outcome.origin?.rawValue ?? "none",
                "translation_calls":outcome.localTranslationCalls,"spans":rows,"speech_segments":segments,
                "policy":"reviewed private provider, no supplied target/span; not runtime activation or acoustic correctness"]
            do {
                let path=FileManager.default.urls(for:.documentDirectory,in:.userDomainMask)[0].appendingPathComponent("frame-route-ui-"+target+".json")
                try JSONSerialization.data(withJSONObject:evidence,options:.sortedKeys).write(to:path)
                proof=(outcome.origin?.rawValue ?? "none")+"|"+String(result.spans.count)+"|"+String(outcome.localTranslationCalls)
                speech.prepare(source:"en",target:target,warmups:["en":"Hello.",target:target == "sw" ? "muziki" : "音楽"])
                ready=true
            } catch { proof="failed:"+String(describing:error) }
        }
        .onChange(of:String(describing:speech.state),initial:true) { _,state in
            speechEvents.append(state)
            let payload:[String:Any] = ["states":speechEvents,"observed_at":Date().timeIntervalSince1970,"active_message":speech.activeMessage as Any? ?? NSNull(),"error":speech.error as Any? ?? NSNull()]
            let path=FileManager.default.urls(for:.documentDirectory,in:.userDomainMask)[0].appendingPathComponent("frame-route-ui-"+target+"-speech-events.json")
            if let bytes=try? JSONSerialization.data(withJSONObject:payload,options:.sortedKeys) { try? bytes.write(to:path,options:.atomic) }
        }
        .onDisappear { owner.close();speech.stop() }
    }
}
#endif
