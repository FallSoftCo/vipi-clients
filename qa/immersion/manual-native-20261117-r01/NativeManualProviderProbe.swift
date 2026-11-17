import Foundation
import Translation
import NaturalLanguage
import VipiCore

struct VipiFocus: AttributedStringKey {
    typealias Value = String
    static let name = "co.fallsoft.vipi.qa.manual-focus"
}

@main struct NativeManualProviderProbe {
    @MainActor static func main() async throws {
        let folder = URL(fileURLWithPath: CommandLine.arguments[1])
        let output = folder.appendingPathComponent("results-r01.json")
        guard !FileManager.default.fileExists(atPath: output.path) else { fatalError("Inspect original results; do not repeat") }
        let cases = try JSONSerialization.jsonObject(with: Data(contentsOf:folder.appendingPathComponent("cases.json"))) as! [[String:String]]
        let reader = try ChineseFullReading(data:Data(contentsOf:folder.appendingPathComponent("chinese-ordinary.json")))
        let availability = LanguageAvailability(preferredStrategy:.lowLatency)
        var rows:[[String:Any]] = []
        func save(_ completed:Bool) throws {
            let report:[String:Any] = ["scope":"Actual native macOS installed Apple Translation lowLatency models through current manual resolver; authored synthetic cases; not mobile gesture or linguistic acceptance",
                "network_disabled":false,"completed":completed,"cases":rows]
            try JSONSerialization.data(withJSONObject:report,options:[.prettyPrinted,.sortedKeys]).write(to:output,options:.atomic)
        }
        for item in cases {
            let id=item["id"]!, original=item["original"]!, focus=item["focus"]!, source=item["source"]!, target=item["target"]!
            let range=(original as NSString).range(of:focus)
            guard range.location != NSNotFound else {fatalError("Invalid fixture range")}
            let request=ManualTranslationRequest(messageID:id,originalText:original,startUTF16:range.location,endUTF16:NSMaxRange(range),
                knownLanguage:source,learningLanguage:target,inputLanguage:source,generation:1,ownerGeneration:UUID())
            var row:[String:Any]=["id":id,"original":original,"selected":focus,"source":source,"target":target]
            let from=Locale.Language(identifier:source),to=Locale.Language(identifier:target)
            let state=await availability.status(from:from,to:to)
            row["availability"]=String(describing:state)
            let start=Date()
            var calls=0
            let outcome=try await ManualTranslationResolver.resolve(request,valid:{true},reference:{_,_,_ in nil},identify:{text in
                let detector=NLLanguageRecognizer();detector.processString(text);return detector.dominantLanguage?.rawValue
            },modelsReady:{_,_ in state == .installed},translate:{text,s,t in
                calls+=1
                let session=TranslationSession(installedSource:Locale.Language(identifier:s),target:Locale.Language(identifier:t),preferredStrategy:.lowLatency)
                defer {session.cancel()}
                return try await session.translate(text).targetText
            },reading:{text,language in
                let reading:String?
                switch language {
                case "zh":reading=try? reader.resolve(text).reading
                case "ja":reading=JapaneseFullReading.resolve(text).reading
                case "ko":reading=KoreanFullReading.resolve(text).reading
                default:reading=nil
                }
                return reading.map {FullReading(text:$0,provenance:.localTransliteration)}
            })
            row["manual_status"]=outcome.status.rawValue;row["manual_seconds"]=Date().timeIntervalSince(start);row["provider_calls"]=calls
            if let result=outcome.result {row["manual_target"]=result.targetText;row["reading"]=result.reading?.text ?? ""}
            // Compare context-preserving full translation and actual attributed
            // focus projection. Neither is silently substituted into the app.
            if state == .installed {
                let session=TranslationSession(installedSource:from,target:to,preferredStrategy:.lowLatency)
                do {
                    let contextual=Date()
                    let full=try await session.translate(original)
                    row["full_target"]=full.targetText
                    var marked=AttributedString(original)
                    if let r=marked.range(of:focus) {marked[r][VipiFocus.self]=id}
                    let projected=try await session.translate(marked)
                    row["attributed_full_target"]=projected.targetText
                    var spans:[String]=[]
                    if let attributed=projected.attributedTargetText {
                        for run in attributed.runs where run[VipiFocus.self] == id {spans.append(String(attributed[run.range].characters))}
                    }
                    row["projected_focus"]=spans;row["context_seconds"]=Date().timeIntervalSince(contextual)
                } catch {row["context_error"]=String(describing:error)}
                session.cancel()
            }
            rows.append(row);try save(false)
        }
        try save(true)
    }
}
