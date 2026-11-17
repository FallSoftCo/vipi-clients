import Foundation
import VipiCore
@main struct ContextProbe {
    @MainActor static func main() async throws {
        let input=try Data(contentsOf:URL(fileURLWithPath:CommandLine.arguments[1]))
        let cases=(try JSONSerialization.jsonObject(with:input) as! [String:Any])["cases"] as! [[String:Any]]
        var rows:[[String:Any]]=[]
        for item in cases {
            let text=item["text"] as! String,a=item["startUTF16"] as! Int,b=item["endUTF16"] as! Int
            let actual=ManualTranslationContext.enclosing(text,start:a,end:b,language:item["language"] as? String)
            precondition(actual.text.utf8.elementsEqual((item["expectedContext"] as! String).utf8),"\(item["id"]!): \(actual.text)")
            precondition(actual.startUTF16==item["expectedStartUTF16"] as! Int && actual.endUTF16==item["expectedEndUTF16"] as! Int)
            precondition((text as NSString).substring(with:NSRange(location:actual.startUTF16,length:actual.endUTF16-actual.startUTF16)).utf8.elementsEqual(actual.text.utf8))
            precondition(actual.startUTF16<=a&&actual.endUTF16>=b)
            rows.append(["id":item["id"]!,"text":actual.text,"start":actual.startUTF16,"end":actual.endUTF16])
        }
        let text="Please book a table tonight.",request=ManualTranslationRequest(messageID:"book-context",originalText:text,startUTF16:7,endUTF16:11,knownLanguage:"en",learningLanguage:"it",inputLanguage:"en",generation:1,ownerGeneration:UUID())
        var translated="",references:[String]=[]
        let result=try await ManualTranslationResolver.resolve(request,valid:{true},reference:{value,_,_ in references.append(value);return value=="book" ? "Libro" : nil},identify:{_ in "en"},modelsReady:{_,_ in true},translate:{value,_,_ in translated=value;return "Prenota un tavolo per stasera."},reading:{_,_ in nil})
        precondition(result.status == .ready && translated==text && !references.contains("book"))
        precondition(result.result?.originalSlice=="book" && result.result?.sourceContextText==text && result.result?.contextExpanded==true)
        let report:[String:Any]=["passed":true,"platform":"native macOS NLTokenizer component, not iOS UI/model acceptance","cases":rows,"isolated_dictionary_bypass_blocked":true]
        try JSONSerialization.data(withJSONObject:report,options:[.prettyPrinted,.sortedKeys,.withoutEscapingSlashes]).write(to:URL(fileURLWithPath:CommandLine.arguments[2]),options:.withoutOverwriting)
        print("Passed \(cases.count) context cases + isolated-reference guard")
    }
}
