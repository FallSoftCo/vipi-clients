import Foundation
import Translation
import NaturalLanguage
import VipiCore

struct VipiFocus: AttributedStringKey {
    typealias Value = String
    static let name = "co.fallsoft.vipi.qa.manual-focus"
}

@main struct NativeContextProviderProbe {
    @MainActor static func main() async throws {
        let folder = URL(fileURLWithPath: CommandLine.arguments[1])
        let output = folder.appendingPathComponent("results-r02.json")
        guard !FileManager.default.fileExists(atPath: output.path) else { fatalError("Inspect original results; do not repeat") }
        let cases = try JSONSerialization.jsonObject(with: Data(contentsOf:folder.appendingPathComponent("cases.json"))) as! [[String:String]]
        let reader = try ChineseFullReading(data:Data(contentsOf:folder.appendingPathComponent("chinese-ordinary.json")))
        let availability = LanguageAvailability(preferredStrategy:.lowLatency)
        var rows:[[String:Any]] = []
        func save(_ completed:Bool) throws {
            let report:[String:Any] = ["scope":"Actual native macOS installed Apple Translation lowLatency models through sentence-context manual resolver; same authored failure cases plus multi-sentence selection; not mobile gesture or linguistic acceptance",
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
            if let result=outcome.result {
                row["manual_target"]=result.targetText;row["reading"]=result.reading?.text ?? ""
                row["source_context"]=result.sourceContextText
                row["source_start_utf16"]=result.sourceContextStartUTF16
                row["source_end_utf16"]=result.sourceContextEndUTF16
                row["context_expanded"]=result.contextExpanded
            }
            rows.append(row);try save(false)
        }
        try save(true)
    }
}
