import Foundation
import Translation

struct FocusID: AttributedStringKey {
    typealias Value = String
    static let name = "co.fallsoft.vipi.qualification.focus-id"
}

@main struct AttributedTranslationProbe {
    @MainActor static func main() async throws {
        let out = URL(fileURLWithPath: CommandLine.arguments[1])
        let fixture = try JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[2]))) as! [String:Any]
        let cases = fixture["cases"] as! [[String:Any]]
        var rows: [[String:Any]] = []
        func save() throws {
            let report: [String:Any] = ["scope":"native macOS installed Apple lowLatency models; synthetic authored cases; no linguistic acceptance", "network_disabled":false, "cases":rows]
            try JSONSerialization.data(withJSONObject:report,options:[.prettyPrinted,.sortedKeys]).write(to:out,options:.atomic)
        }
        let availability = LanguageAvailability(preferredStrategy:.lowLatency)
        for input in cases {
            let id=input["id"] as! String, source=input["source_language"] as! String, target=input["target_language"] as! String
            let text=input["original"] as! String, focus=input["focus"] as! String
            let offsets=input["focus_utf16"] as! [Int]
            guard offsets.count == 2, offsets[1] >= offsets[0], (text as NSString).substring(with: NSRange(location:offsets[0],length:offsets[1]-offsets[0])) == focus else { throw NSError(domain:"fixture",code:1) }
            var row: [String:Any] = ["id":id,"source":source,"target":target,"text":text,"focus":focus]
            let from=Locale.Language(identifier:source), to=Locale.Language(identifier:target)
            let state = await availability.status(from:from,to:to)
            row["availability"] = String(describing:state)
            guard state == .installed else { row["status"]="not_installed"; rows.append(row); try save(); continue }
            let session=TranslationSession(installedSource:from,target:to,preferredStrategy:.lowLatency)
            do {
                var attributed=AttributedString(text)
                guard let range=attributed.range(of:focus) else { throw NSError(domain:"focus",code:1) }
                attributed[range][FocusID.self] = id
                let start=Date()
                let full=try await session.translate(text)
                let isolated=try await session.translate(focus)
                let contextual=try await session.translate(attributed)
                var selective=AttributedString(text)
                guard let selected=selective.range(of:focus) else { throw NSError(domain:"focus",code:2) }
                if selected.lowerBound != selective.startIndex { selective[selective.startIndex..<selected.lowerBound].skipsTranslation = true }
                if selected.upperBound != selective.endIndex { selective[selected.upperBound..<selective.endIndex].skipsTranslation = true }
                let selectiveStart=Date()
                let mixed=try await session.translate(selective)
                row["selective_mixed"] = mixed.targetText
                row["selective_seconds"] = Date().timeIntervalSince(selectiveStart)
                let ns=text as NSString
                let prefix=ns.substring(to:offsets[0]), suffix=ns.substring(from:offsets[1])
                row["outside_preserved_in_order"] = mixed.targetText.hasPrefix(prefix) && mixed.targetText.hasSuffix(suffix) && mixed.targetText.utf16.count >= prefix.utf16.count + suffix.utf16.count
                row["full"] = full.targetText
                row["isolated"] = isolated.targetText
                row["attributed_full"] = contextual.targetText
                row["elapsed_seconds"] = Date().timeIntervalSince(start)
                if let result=contextual.attributedTargetText {
                    var segments:[[String:String]]=[]
                    for run in result.runs {
                        if let marker=run[FocusID.self] {
                            segments.append(["marker":marker,"text":String(result[run.range].characters)])
                        }
                    }
                    row["marked_target_runs"]=segments
                } else { row["marked_target_runs"]=[] }
                row["status"]="translated"
            } catch { row["status"]="failed";row["error"]=String(describing:error) }
            session.cancel()
            rows.append(row);try save()
        }
    }
}
