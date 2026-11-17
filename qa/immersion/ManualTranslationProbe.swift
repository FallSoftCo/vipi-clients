import Foundation
import VipiCore

@main struct ManualTranslationProbe {
    @MainActor static func main() async throws {
        let epoch = UUID()
        func request(_ text:String, _ start:Int = 0, _ end:Int? = nil, _ known:String = "en", _ learning:String = "zh", _ input:String? = nil, _ generation:UInt64 = 1) -> ManualTranslationRequest {
            .init(messageID:"immutable-message",originalText:text,startUTF16:start,endUTF16:end ?? text.utf16.count,knownLanguage:known,learningLanguage:learning,inputLanguage:input,generation:generation,ownerGeneration:epoch)
        }
        let reader = try ChineseFullReading(data:Data(contentsOf:URL(fileURLWithPath:CommandLine.arguments[1])))
        var valid = true, calls = 0, readingCalls = 0
        var translatedInput = "", detectedInput = "", translatedDirection = ""
        func run(_ selection:ManualTranslationRequest, output:String = "音乐", ready:Bool = true, stale:Bool = false) async throws -> ManualTranslationOutcome {
            try await ManualTranslationResolver.resolve(selection,valid:{valid},reference:{ _,_,_ in nil },
                identify:{ text in detectedInput=text; return selection.knownLanguage }, modelsReady:{ _,_ in ready },
                translate:{ text,from,to in calls+=1;translatedInput=text;translatedDirection=from+"-"+to;if stale {valid=false};return output },
                reading:{ text,language in readingCalls+=1;guard language == "zh",let value=try? reader.resolve(text).reading else{return nil};return .init(text:value,provenance:.localTransliteration) })
        }
        let selected = request("We discussed music after dinner.",13,18)
        let first = try await run(selected)
        precondition(first.status == .ready && first.result?.originalSlice == "music" && translatedInput == "music")
        precondition(first.result?.targetText == "音乐" && first.result?.reading?.text == "yīnyuè" && calls == 1)
        precondition(first.result?.request == selected && first.result?.sourceLanguage == "en" && first.result?.targetLanguage == "zh")
        let reverse = try await run(request("银行"),output:"bank")
        precondition(reverse.status == .ready && translatedDirection == "zh-en" && reverse.result?.reading == nil)
        let context = request("I would like to know what this word means.",2,7,"en","fr")
        _ = try await run(context,output:"voudrais")
        precondition(detectedInput == context.originalText && translatedInput == "would")
        let explicit = try await run(request("chat",0,nil,"en","fr","fr"),output:"cat")
        precondition(explicit.status == .ready && translatedDirection == "fr-en")
        precondition(ManualTranslationResolver.slice(request("A😀B",2,3)) == nil)
        precondition(ManualTranslationResolver.slice(request("e\u{301}",0,1)) == nil)
        let canonA = request("café"), canonB = request("cafe\u{301}")
        precondition(canonA.selectionIdentity != canonB.selectionIdentity && canonA != canonB)
        precondition(request("word",0,nil,"en","zh",nil,2) != request("word"))
        let callsBefore = calls
        let missing = try await run(request("word"),ready:false)
        precondition(missing.status == .modelNotReady && calls == callsBefore)
        let integrity = try await run(request("Read notes.md"),output:"阅读")
        precondition(integrity.status == .invalidResult)
        let readsBefore = readingCalls
        let stale = try await run(request("word"),stale:true)
        precondition(stale.status == .stale && stale.result == nil && readingCalls == readsBefore)
        valid=true
        let timeout = try await ManualTranslationResolver.resolve(request("word"),valid:{true},reference:{_,_,_ in nil},identify:{_ in "en"},modelsReady:{_,_ in true},translate:{_,_,_ in throw ManualTranslationFailure.timeout},reading:{_,_ in nil})
        precondition(timeout.status == .timeout)
        do {
            _ = try await ManualTranslationResolver.resolve(request("word"),valid:{true},reference:{_,_,_ in nil},identify:{_ in "en"},modelsReady:{_,_ in true},translate:{_,_,_ in throw CancellationError()},reading:{_,_ in nil})
            fatalError("cancelled request published")
        } catch is CancellationError { }
        let longContext=String(repeating:"word ",count:6000)
        let longSelection=request(longContext,longContext.utf16.count-5,longContext.utf16.count-1)
        let selectedLong=try await run(longSelection)
        precondition(selectedLong.status == .ready && selectedLong.result?.originalSlice == "word")
        let longURL="https://example.test/"+String(repeating:"x",count:9000)
        let longWhole="Go "+longURL+" now "+String(repeating:"words ",count:2500)
        var chunks=0
        let chunked=try await ManualTranslationResolver.resolve(request(longWhole),valid:{true},reference:{_,_,_ in nil},identify:{_ in "en"},modelsReady:{_,_ in true},translate:{text,_,_ in
            precondition(text.utf16.count <= 8192 && !text.contains("https://"));chunks+=1;return text
        },reading:{_,_ in nil})
        precondition(chunked.status == .ready && chunked.result?.targetText == longWhole && chunks>=2)
        let report:[String:Any] = ["platform":"native macOS Swift CLI; component behavior, not app rendering or model quality","checks":["arbitrary word with no alignment","actual marked Chinese reading","reverse direction","whole-original context for ambiguous slice","explicit input language","UTF16 surrogate and composed boundaries","exact UTF8 identity","selection generation","missing model without inference","literal integrity","late-result suppression","timeout distinction","cancellation propagation","word in valid 30KiB original","whole-message chunk/literal preservation"],"passed":true,"translation_calls":calls,"reading_calls":readingCalls]
        try JSONSerialization.data(withJSONObject:report,options:[.prettyPrinted,.sortedKeys]).write(to:URL(fileURLWithPath:CommandLine.arguments[2]),options:.withoutOverwriting)
    }
}
