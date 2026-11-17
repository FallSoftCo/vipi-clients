import Foundation

@main struct ArabicRendererProbe {
    static func main() throws {
        let directory=URL(fileURLWithPath:CommandLine.arguments[1])
        let data=try Data(contentsOf:directory.appendingPathComponent("renderer-regressions.json"))
        let cases=(try JSONSerialization.jsonObject(with:data) as! [String:Any])["cases"] as! [[String:Any]]
        var rows:[[String:Any]]=[]
        for item in cases {
            let text=item["text"] as! String,expected=item["expected"] as? String
            let result=ArabicVocalizedReading.resolve(text)
            precondition(result.reading==expected,"\(item["id"]!): \(result.reading ?? "nil") != \(expected ?? "nil")")
            precondition(result.pieces.map(\.source).joined().utf8.elementsEqual(text.utf8))
            precondition(result.pieces.filter(\.protected).allSatisfy{$0.source.utf8.elementsEqual(($0.reading ?? "").utf8)})
            rows.append(["id":item["id"]!,"source":text,"reading":result.reading as Any? ?? NSNull(),"partition_exact":true])
        }
        let candidates=(try JSONSerialization.jsonObject(with:Data(contentsOf:directory.appendingPathComponent("qualification-results-r02.json"))) as! [String:Any])["cases"] as! [[String:Any]]
        let inferred=candidates.map { row -> [String:Any] in
            let script=row["preserving_derived_metadata"] as! String
            return ["id":row["id"]!,"category":row["category"]!,"model_script":script,"candidate_reading":ArabicVocalizedReading.resolve(script).reading as Any? ?? NSNull()]
        }
        let report:[String:Any]=["platform":"native macOS Swift CLI; dormant renderer component, not iOS execution","passed":true,"regressions":rows,"unaccepted_model_inference_readings":inferred]
        try JSONSerialization.data(withJSONObject:report,options:[.prettyPrinted,.sortedKeys,.withoutEscapingSlashes]).write(to:directory.appendingPathComponent("renderer-native-swift-results.json"),options:.withoutOverwriting)
        print("Passed \(cases.count) Swift renderer regressions")
    }
}
