import Foundation

@main struct ArabicLatinProbe {
    static func main() throws {
        let input=try Data(contentsOf:URL(fileURLWithPath:CommandLine.arguments[1]))
        let report=try JSONSerialization.jsonObject(with:input) as! [String:Any]
        let rows=report["cases"] as! [[String:Any]]
        var outputs:[[String:Any]]=[]
        for row in rows {
            let pieces=row["pieces"] as! [[String:Any]]
            var output="",run=""
            func flush() {
                guard !run.isEmpty else{return}
                output+=(run.applyingTransform(.toLatin,reverse:false) ?? run).replacingOccurrences(of:"ʿ",with:"'").replacingOccurrences(of:"ʾ",with:"'")
                run=""
            }
            for piece in pieces {
                let derived=piece["derived"] as! String
                if piece["protected"] as! Bool {flush();output+=derived;continue}
                if derived.range(of:#"\p{Arabic}"#,options:.regularExpression) != nil {run+=derived}
                else {flush();output+=derived}
            }
            flush()
            outputs.append(["id":row["id"]!,"source":row["text"]!,"derived_script":row["preserving_derived_metadata"]!,"candidate_latin":output])
        }
        let value:[String:Any]=["platform":"native macOS Foundation toLatin transform of Arabic runs only","production_enabled":false,"interpretation":"Candidate Latin conversion for review, not certified pronunciation. Existing protected literals remain exact; irregular orthography/assimilation and dialect still need qualification.","cases":outputs]
        try JSONSerialization.data(withJSONObject:value,options:[.prettyPrinted,.sortedKeys,.withoutEscapingSlashes]).write(to:URL(fileURLWithPath:CommandLine.arguments[2]),options:.withoutOverwriting)
    }
}
