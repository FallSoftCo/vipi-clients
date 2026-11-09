import Foundation
import NaturalLanguage

@main struct NativeContextPackProbe {
    static func words(_ text: String) -> [NSRange] {
        let tokenizer = NLTokenizer(unit:.word);tokenizer.string=text;tokenizer.setLanguage(.english)
        var result:[NSRange]=[]
        tokenizer.enumerateTokens(in:text.startIndex..<text.endIndex) { range,_ in
            if text[range].unicodeScalars.contains(where:{CharacterSet.letters.contains($0)}) { result.append(NSRange(range,in:text)) };return true
        };return result
    }
    static func main() throws {
        guard CommandLine.arguments.count == 4 else { throw NSError(domain:"arguments",code:1) }
        let root=URL(fileURLWithPath:CommandLine.arguments[1]), en=URL(fileURLWithPath:CommandLine.arguments[2])
        let config=try JSONSerialization.jsonObject(with:Data(contentsOf:root.appendingPathComponent("native-bindings.json"))) as! [String:Any]
        let pack=try FrozenContextPack(url:root.appendingPathComponent("context.sqlite"),expectedSHA256:"cd7a8667ff0df53610ef19aa585398e24470716dd23af6d640b7c77dbc3badb4",expectedMetadata:config["expected_metadata"] as! [String:String],dictionaryURLs:["en":en,"es":root.appendingPathComponent("d-es.sqlite")])
        let fixtures=try JSONSerialization.jsonObject(with:Data(contentsOf:root.appendingPathComponent("rule-fixtures.json"))) as! [String:Any]
        var observations:[[String:Any]]=[]
        for row in fixtures["rows"] as! [[String:Any]] {
            let text=row["source"] as! String,id=row["rule_id"] as! String
            guard row["roundtrip"] as? Bool == true else { observations.append(["rule_id":id,"status":"fixture_retokenization_changed"]);continue }
            let ranges=(row["ranges"] as! [[Int]]).map { NSRange(location:$0[0],length:$0[1]) }, focus=row["focus"] as! [Int]
            let native=words(text)
            guard native.contains(NSRange(location:focus[0],length:focus[1])) else { observations.append(["rule_id":id,"status":"native_geometry_difference","native":native.map { [$0.location,$0.length] }]);continue }
            let start=DispatchTime.now().uptimeNanoseconds
            let assessment=try pack.assess(original:text,nativeWordRanges:native,focus:.init(location:focus[0],length:focus[1]),sourceKeys:row["source_keys"] as! [String])
            let winner=assessment.winner
            let expected=row["winner"] as? [String:Any]
            let equal=winner?.rule.id == expected?["id"] as? String && winner?.rule.headIDs == expected?["head_ids"] as? [String]
            observations.append(["rule_id":id,"status":winner == nil ? "no_match":"matched","winner":winner?.rule.id as Any? ?? NSNull(),"heads":winner?.rule.headIDs as Any? ?? NSNull(),"context_geometry_compatible":winner?.contextGeometryCompatible as Any? ?? NSNull(),"whole_native_geometry_equal":native==ranges,"expected_equal":equal,"elapsed_ns":DispatchTime.now().uptimeNanoseconds-start])
        }
        // Actual native geometry on retained complete messages; not synthetic rule spans.
        let sourceFixture = try JSONSerialization.jsonObject(with: Data(base64Encoded: EnglishSourceRoleFixture.base64)!) as! [String: Any]
        var fullSources: [[String: Any]] = []
        var keysBySpelling: [Data: [String]] = [:]
        for key in Dictionary(grouping:pack.rules.map(\.sourceKey),by:{Data($0.utf8)}).values.map({$0[0]}) {
            let parts = try JSONSerialization.jsonObject(with: Data(key.utf8)) as! [Any]
            keysBySpelling[Data((parts[0] as! String).utf8), default: []].append(key)
        }
        let fullTokenizer = try FrozenContextTokenizer()
        for row in sourceFixture["cases"] as! [[String: Any]] {
            let source = row["source"] as! String
            let current = words(source)
            let retained = (row["native_words_utf16"] as! [[Int]]).map { NSRange(location:$0[0],length:$0[1]-$0[0]) }
            var focuses: [[String: Any]] = []
            for focus in current {
                let piece = (source as NSString).substring(with: focus)
                let key = try fullTokenizer.normalize(piece)
                let keys = keysBySpelling[Data(key.utf8)] ?? []
                if keys.isEmpty { continue }
                let a = try pack.assess(original:source,nativeWordRanges:current,focus:focus,sourceKeys:keys)
                let prior = retained.contains(focus) ? try pack.assess(original:source,nativeWordRanges:retained,focus:focus,sourceKeys:keys) : nil
                focuses.append(["focus":[focus.location,focus.length],"source":piece,
                    "current_winner":a.winner?.rule.id as Any? ?? NSNull(),
                    "retained_geometry_winner":prior?.winner?.rule.id as Any? ?? NSNull(),
                    "retained_contains_focus":retained.contains(focus),
                    "current_geometry_rejections":a.rawMatches.filter { !$0.contextGeometryCompatible }.map { $0.rule.id }])
            }
            fullSources.append(["case_id":row["case_id"]!,"source_id":row["source_id"]!,"source":source,
                "current_native_ranges":current.map { [$0.location,$0.length] },"retained_geometry_equal":current == retained,
                "focuses":focuses,"scope":"All source-spelling keys diagnostic, not eligible-head candidate set; no catalog selection, role inference, source-mask approval or output admission"])
        }
        let tokenizer=try FrozenContextTokenizer()
        let tokenFixture=try JSONSerialization.jsonObject(with:Data(base64Encoded:FrozenContextTokenizerFixture.base64)!) as! [String:Any]
        var tokenResults:[[String:Any]]=[]
        for row in tokenFixture["cases"] as! [[String:Any]] {
            let text=row["source"] as! String
            do {
                let tokens=try tokenizer.tokenize(text)
                tokenResults.append(["source":text,"supported":true,"normalized":try tokenizer.normalize(text),"tokens":tokens.map { ["text":$0.original,"normalized":$0.normalized,"range":[$0.range.location,$0.range.length],"has_alpha":$0.hasAlphabeticScalar] as [String:Any] }])
            } catch FrozenContextTokenizer.Failure.unsupportedScalar { tokenResults.append(["source":text,"supported":false]) }
        }
        let output:[String:Any]=["schema":"vipi.native-context-pack-probe.r01","os":ProcessInfo.processInfo.operatingSystemVersionString,"rules":pack.rules.count,"heads":pack.heads.count,"no_head_rules":pack.rules.filter{$0.headIDs.isEmpty}.count,"observations":observations,"full_sources":fullSources,"tokenizer":tokenResults,"scope":"Uncalled research matcher; no meaning/permission/selector activation"]
        let data=try JSONSerialization.data(withJSONObject:output,options:[.sortedKeys]);guard data.count<=4*1024*1024 else { throw NSError(domain:"output_bound",code:1) }
        try data.write(to:URL(fileURLWithPath:CommandLine.arguments[3]),options:.atomic)
    }
}
