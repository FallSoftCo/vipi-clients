import Foundation
import NaturalLanguage

@main struct NLTaggerProbe {
    static func main() throws {
        let input = URL(fileURLWithPath:CommandLine.arguments[1]), output = URL(fileURLWithPath:CommandLine.arguments[2])
        let fixture = try JSONSerialization.jsonObject(with:Data(contentsOf:input)) as! [String:Any]
        let codes=["en","es","fr","de","it","pt","ar","zh","ja","ko","sw"]
        let languages: [[String:Any]] = codes.map { code in
            let language=NLLanguage(rawValue:code)
            return ["language":code,"schemes":NLTagger.availableTagSchemes(for:.word,language:language).map(\.rawValue).sorted()]
        }
        var cases:[[String:Any]]=[]
        for input in fixture["cases"] as! [[String:Any]] {
            let text=input["original"] as! String, source=input["source_language"] as! String
            let language=NLLanguage(rawValue:source)
            let available=NLTagger.availableTagSchemes(for:.word,language:language)
            let tagger=NLTagger(tagSchemes:[.lexicalClass,.lemma]);tagger.string=text
            tagger.setLanguage(language,range:text.startIndex..<text.endIndex)
            var tags:[[String:Any]]=[]
            if available.contains(.lexicalClass) {
                tagger.enumerateTags(in:text.startIndex..<text.endIndex,unit:.word,scheme:.lexicalClass,options:[]) { tag, range in
                    let ns=NSRange(range,in:text)
                    tags.append(["text":String(text[range]),"start_utf16":ns.location,"end_utf16":NSMaxRange(ns),"lexical_class":tag?.rawValue as Any? ?? NSNull()])
                    return true
                }
            }
            var lemmas:[[String:Any]]=[]
            if available.contains(.lemma) {
                tagger.enumerateTags(in:text.startIndex..<text.endIndex,unit:.word,scheme:.lemma,options:[]) { tag,range in
                    let ns=NSRange(range,in:text)
                    lemmas.append(["text":String(text[range]),"start_utf16":ns.location,"end_utf16":NSMaxRange(ns),"lemma":tag?.rawValue as Any? ?? NSNull()]);return true
                }
            }
            cases.append(["id":input["id"]!,"source":source,"original":text,"focus":input["focus"]!,"tags":tags,"lemmas":lemmas])
        }
        let result:[String:Any]=["scope":"native macOS language-specific system tagger; authored fixture, not iOS or linguistic acceptance", "languages":languages,"cases":cases]
        try JSONSerialization.data(withJSONObject:result,options:[.prettyPrinted,.sortedKeys]).write(to:output,options:.withoutOverwriting)
    }
}
