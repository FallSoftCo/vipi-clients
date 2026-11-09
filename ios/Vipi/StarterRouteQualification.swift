#if DEBUG
import SwiftUI
import VipiCore

/// Isolated original-message host. Targets and spans come only from the default provider.
@MainActor struct StarterRouteQualificationView: View {
    @State private var owner = ConversationImmersion(modelStatus: { _ in .unsupported })
    @State private var speech = SpeechPlayback()
    @State private var ready = false
    @State private var proof = "pending"
    @State private var speechEvents = [String]()
    private var packed: Bool { ProcessInfo.processInfo.arguments.contains("-vipi-starter-packed") }
    private var original: String { packed ? "My family and my family enjoy pizza." : "Country music is fun!" }
    private var density: Double { packed ? 0.75 : 0.25 }
    private var target: String { ProcessInfo.processInfo.arguments.contains("-vipi-starter-sw") ? "sw" : "ja" }
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment:.leading,spacing:16) {
                    Text("Default source-first chat connection QA").font(.footnote)
                    if ready {
                        ConversationImmersionText(text:original,id:"starter-ui-"+target,immersion:owner,speech:speech,
                            paused:false,metadata:AnyView(Text("Owned local message")),onVoiceHelp:{})
                    }
                    Text(proof).font(.caption).accessibilityIdentifier("starter-route-proof")
                    Text(String(describing:speech.state)).font(.caption).accessibilityIdentifier("starter-route-speech-state")
                    Text(speechEvents.joined(separator:"|")).font(.caption).accessibilityIdentifier("starter-route-speech-events")
                }.padding()
            }.navigationTitle(target == "sw" ? "Swahili source route" : "Japanese source route")
        }
        .task {
            let id = "starter-ui-"+target
            await owner.configure(pair:.init(source:"en",target:target),density:density,knownConceptIDs:[])
            owner.selectInputLanguage("en",for:id)
            _ = await owner.result(for:original,inputLanguage:"en",messageID:id)
            guard let outcome=owner.lastOutcome,let result=outcome.result else { proof="failed:no result";return }
            let segments=result.speech(source:"en",target:target).map { ["text":$0.text,"language":$0.language] }
            let rows=result.spans.map { ["source":$0.original,"target":$0.translated,"reading":$0.romanization as Any? ?? NSNull(),"scope":[$0.range.location,NSMaxRange($0.range)]] as [String:Any] }
            let evidence:[String:Any] = ["original":original,"target":target,"density":density,"known_ids":[String](),
                "provider_identity":BundledStarterLookup.provider()?.identity ?? "missing","origin":outcome.origin?.rawValue ?? "none",
                "translation_calls":outcome.localTranslationCalls,"spans":rows,"speech_segments":segments,
                "policy":"actual default provider result, no supplied target/span; speech segments do not certify acoustic correctness"]
            do {
                let path=FileManager.default.urls(for:.documentDirectory,in:.userDomainMask)[0].appendingPathComponent("starter-route-ui-"+target+".json")
                try JSONSerialization.data(withJSONObject:evidence,options:.sortedKeys).write(to:path)
                proof=(outcome.origin?.rawValue ?? "none")+"|"+String(result.spans.count)+"|"+String(outcome.localTranslationCalls)
                speech.prepare(source:"en",target:target,warmups:["en":"Hello.",target:target == "sw" ? "muziki" : "音楽"])
                ready=true
            } catch { proof="failed:"+String(describing:error) }
        }
        .onChange(of:String(describing:speech.state),initial:true) { _,state in
            speechEvents.append(state)
            let payload:[String:Any] = ["states":speechEvents,"observed_at":Date().timeIntervalSince1970,"active_message":speech.activeMessage as Any? ?? NSNull(),"error":speech.error as Any? ?? NSNull()]
            let path=FileManager.default.urls(for:.documentDirectory,in:.userDomainMask)[0].appendingPathComponent("starter-route-ui-"+target+"-speech-events.json")
            if let bytes=try? JSONSerialization.data(withJSONObject:payload,options:.sortedKeys) { try? bytes.write(to:path,options:.atomic) }
        }
        .onDisappear { owner.close();speech.stop() }
    }
}
#endif
