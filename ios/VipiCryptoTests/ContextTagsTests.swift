import CryptoKit
import Foundation
import NaturalLanguage
import XCTest
@testable import Vipi

/// Diagnostic only. Built-in tags are observations, not semantic authority.
final class ContextTagsTests: XCTestCase {
    private final class AssetCompletion:@unchecked Sendable {
        private let lock=NSLock()
        private var continuation:CheckedContinuation<String,Never>?
        init(_ continuation:CheckedContinuation<String,Never>) {self.continuation=continuation}
        func finish(_ value:String) {
            lock.lock();let pending=continuation;continuation=nil;lock.unlock()
            pending?.resume(returning:value)
        }
    }
    private static func request(_ language:NLLanguage,_ scheme:NLTagScheme) async -> String {
        await withCheckedContinuation { continuation in
            let completion=AssetCompletion(continuation)
            // Diagnostic timeout only: the framework may continue its download.
            DispatchQueue.global().asyncAfter(deadline:.now()+15) {completion.finish("timeout; availability unresolved")}
            NLTagger.requestAssets(for:language,tagScheme:scheme) {result,error in
                completion.finish(error.map{String(describing:$0)} ?? (result == .available ? "available" : result == .notAvailable ? "not_available" : "error"))
            }
        }
    }
    func testNativeLexicalAndNameEvidence() async throws {
        let root=FileManager.default.urls(for:.documentDirectory,in:.userDomainMask)[0]
        let configURL=root.appendingPathComponent("context-tags-config.json")
        let config: [String:Any] = FileManager.default.fileExists(atPath:configURL.path)
            ? try XCTUnwrap(JSONSerialization.jsonObject(with:Data(contentsOf:configURL)) as? [String:Any]) : [:]
        let revision=config["revision"] as? String ?? "001"
        XCTAssertNotNil(revision.range(of:"^[0-9]{3}$",options:.regularExpression))
        let output=root.appendingPathComponent("context-tags-apple-\(revision).json")
        guard !FileManager.default.fileExists(atPath:output.path) else {XCTFail("Preserve diagnostics");return}
        var inputs:[String:(String,String)]=[:],hashes:[String:String]=[:]
        for name in ["conversation-records.jsonl","conversation-records-expanded-002.jsonl"] {
            let data=try Data(contentsOf:root.appendingPathComponent(name))
            hashes[name]=SHA256.hash(data:data).map{String(format:"%02x",$0)}.joined()
            for line in try XCTUnwrap(String(data:data,encoding:.utf8)).split(separator:"\n") {
                let row=try XCTUnwrap(JSONSerialization.jsonObject(with:Data(line.utf8)) as? [String:Any])
                let source=try XCTUnwrap(row["source_language"] as? String),text=try XCTUnwrap(row["source_context"] as? String)
                inputs[source+":"+text]=(source,text)
            }
        }
        let smsName="bilingual-qa/apple-sms-translations-001.json"
        let sms=try Data(contentsOf:root.appendingPathComponent(smsName))
        hashes[smsName]=SHA256.hash(data:sms).map{String(format:"%02x",$0)}.joined()
        let report=try XCTUnwrap(JSONSerialization.jsonObject(with:sms) as? [String:Any])
        for pair in try XCTUnwrap(report["results"] as? [[String:Any]]) {
            let source=try XCTUnwrap(pair["source"] as? String)
            for sample in try XCTUnwrap(pair["samples"] as? [[String:Any]]) {
                let text=try XCTUnwrap(sample["original"] as? String)
                inputs[source+":"+text]=(source,text)
            }
        }
        let languages=Set(inputs.values.map{$0.0})
        XCTAssertEqual(languages,Set(["en","es","fr","de","it","pt","ar","zh","ja","ko"]))
        func nativeLanguage(_ code:String)->NLLanguage { code=="zh" ? .simplifiedChinese : .init(rawValue:code) }
        var available:[String:[String]]=[:],results:[[String:Any]]=[],assets:[[String:Any]]=[]
        if config["prepare_assets"] as? Bool == true {
            let requests=await withTaskGroup(of:(String,String,String,Bool).self) {group in
                for language in languages.sorted() {for scheme in [NLTagScheme.lexicalClass,.nameType,.lemma] {
                    let native=nativeLanguage(language)
                    group.addTask {
                        let before=NLTagger.availableTagSchemes(for:.word,language:native).contains(scheme)
                        let status=before ? "already_available" : await Self.request(native,scheme)
                        return (language,scheme.rawValue,status,NLTagger.availableTagSchemes(for:.word,language:native).contains(scheme))
                    }
                }}
                var values:[(String,String,String,Bool)]=[]
                for await value in group {values.append(value)}
                return values.sorted{($0.0,$0.1)<($1.0,$1.1)}
            }
            assets=requests.map{["language":$0.0,"scheme":$0.1,"status":$0.2,"available_after":$0.3]}
            try JSONSerialization.data(withJSONObject:assets,options:[.prettyPrinted,.sortedKeys])
                .write(to:root.appendingPathComponent("context-assets-apple-\(revision).json"),options:.atomic)
        }
        for language in languages.sorted() {
            available[language]=NLTagger.availableTagSchemes(for:.word,language:nativeLanguage(language)).map(\.rawValue).sorted()
        }
        for key in inputs.keys.sorted() {
            let (language,text)=inputs[key]!
            let start=ContinuousClock.now
            let tagger=NLTagger(tagSchemes:[.lexicalClass,.nameType,.lemma])
            tagger.string=text;tagger.setLanguage(nativeLanguage(language),range:text.startIndex..<text.endIndex)
            var tokens:[[String:Any]]=[]
            tagger.enumerateTags(in:text.startIndex..<text.endIndex,unit:.word,scheme:.lexicalClass,
                options:[.omitWhitespace,.omitPunctuation]) { tag,range in
                let offset=NSRange(range,in:text)
                let name=tagger.tag(at:range.lowerBound,unit:.word,scheme:.nameType).0?.rawValue
                let lemma=tagger.tag(at:range.lowerBound,unit:.word,scheme:.lemma).0?.rawValue
                tokens.append(["text":String(text[range]),"start":offset.location,"end":NSMaxRange(offset),
                    "lexical_class":tag?.rawValue as Any? ?? NSNull(),"name_type":name as Any? ?? NSNull(),
                    "lemma":lemma as Any? ?? NSNull()])
                return true
            }
            let duration=start.duration(to:.now).components
            results.append(["language":language,"original":text,"tokens":tokens,
                "milliseconds":Double(duration.seconds)*1000+Double(duration.attoseconds)/1e15])
        }
        let receipt:[String:Any]=["schema":"vipi-native-context-tags-1","platform":"Physical iOS device",
            "input_sha256":hashes,"available_schemes":available,"asset_requests":assets,"results":results,
            "network_absence_verified":false,"linguistic_acceptance":false,"runtime_integration":false,
            "scope":"Observed native lexical/name/lemma tags on authored development and diagnostic public SMS; no gold POS/NER annotation"]
        try JSONSerialization.data(withJSONObject:receipt,options:[.prettyPrinted,.sortedKeys]).write(to:output,options:.atomic)
    }
}
