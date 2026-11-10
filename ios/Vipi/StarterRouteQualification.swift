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
    private func argument(_ name: String) -> String? {
        let args = ProcessInfo.processInfo.arguments
        guard let index = args.firstIndex(of: name), args.indices.contains(index + 1) else { return nil }
        return args[index + 1]
    }
    private var source: String { argument("-vipi-starter-source") ?? "en" }
    private var automatic: Bool { ProcessInfo.processInfo.arguments.contains("-vipi-starter-auto") }
    private var receiptID: String { argument("-vipi-starter-source") == nil ? target : source + "-" + target }
    private var packed: Bool { ProcessInfo.processInfo.arguments.contains("-vipi-starter-packed") }
    private var expanded: Bool { ProcessInfo.processInfo.arguments.contains("-vipi-starter-expanded") }
    private var original: String { argument("-vipi-starter-original") ?? (expanded ? "The coffee and bread are for lunch." : packed ? "My family and my family enjoy pizza." : "Country music is fun!") }
    private var density: Double { packed || expanded ? 0.75 : 0.25 }
    private var target: String { argument("-vipi-starter-target") ?? (ProcessInfo.processInfo.arguments.contains("-vipi-starter-sw") ? "sw" : "ja") }
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment:.leading,spacing:16) {
                    Text("Default source-first chat connection QA").font(.footnote)
                    if ready {
                        ConversationImmersionText(text:original,id:"starter-ui-"+receiptID,immersion:owner,speech:speech,
                            paused:false,metadata:AnyView(Text("Owned local message")),onVoiceHelp:{})
                    }
                    Text(proof).font(.caption).accessibilityIdentifier("starter-route-proof")
                    Text(String(describing:speech.state)).font(.caption).accessibilityIdentifier("starter-route-speech-state")
                    Text(speechEvents.joined(separator:"|")).font(.caption).accessibilityIdentifier("starter-route-speech-events")
                }.padding()
            }.navigationTitle(argument("-vipi-starter-source") == nil ? (target == "sw" ? "Swahili source route" : "Japanese source route") : source.uppercased() + " → " + target.uppercased())
        }
        .task {
            let id = "starter-ui-"+receiptID
            await owner.configure(pair:.init(source:source,target:target),density:density,knownConceptIDs:[])
            guard SourceFrameLookup.languages.contains(source), SourceFrameLookup.languages.contains(target), source != target, original.utf16.count <= 16_384 else { proof="failed:invalid pair or input";return }
            if !automatic { owner.selectInputLanguage(source,for:id) }
            _ = await owner.result(for:original,inputLanguage:automatic ? nil : source,messageID:id)
            guard let outcome=owner.lastOutcome,let result=outcome.result else { proof="failed:no result";return }
            let segments=result.speech(source:source,target:target).map { ["text":$0.text,"language":$0.language] }
            let rows=result.spans.map { ["source":$0.original,"target":$0.translated,"reading":$0.romanization as Any? ?? NSNull(),"scope":[$0.range.location,NSMaxRange($0.range)]] as [String:Any] }
            let evidence:[String:Any] = ["original":original,"source":source,"automatic":automatic,"target":target,"density":density,"known_ids":[String](),
                "provider_identity":BundledStarterLookup.provider()?.identity ?? "missing","origin":outcome.origin?.rawValue ?? "none",
                "translation_calls":outcome.localTranslationCalls,"spans":rows,"speech_segments":segments,
                "policy":"actual default provider result, no supplied target/span; speech segments do not certify acoustic correctness"]
            do {
                let path=FileManager.default.urls(for:.documentDirectory,in:.userDomainMask)[0].appendingPathComponent("starter-route-ui-"+receiptID+".json")
                try JSONSerialization.data(withJSONObject:evidence,options:.sortedKeys).write(to:path)
                proof=(outcome.origin?.rawValue ?? "none")+"|"+String(result.spans.count)+"|"+String(outcome.localTranslationCalls)
                let warmups = argument("-vipi-starter-source") == nil ? ["en":"Hello.",target:target == "sw" ? "muziki" : "音楽"] : [source:original,target:result.spans.first?.translated ?? ""]
                speech.prepare(source:source,target:target,warmups:warmups)
                ready=true
            } catch { proof="failed:"+String(describing:error) }
        }
        .onChange(of:String(describing:speech.state),initial:true) { _,state in
            speechEvents.append(state)
            let payload:[String:Any] = ["states":speechEvents,"observed_at":Date().timeIntervalSince1970,"active_message":speech.activeMessage as Any? ?? NSNull(),"error":speech.error as Any? ?? NSNull()]
            let path=FileManager.default.urls(for:.documentDirectory,in:.userDomainMask)[0].appendingPathComponent("starter-route-ui-"+receiptID+"-speech-events.json")
            if let bytes=try? JSONSerialization.data(withJSONObject:payload,options:.sortedKeys) { try? bytes.write(to:path,options:.atomic) }
        }
        .onDisappear { owner.close();speech.stop() }
    }
}
#endif
