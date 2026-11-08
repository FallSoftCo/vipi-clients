import Foundation
import NaturalLanguage
import Darwin

func residentBytes() -> UInt64? {
    var info = mach_task_basic_info()
    var count = mach_msg_type_number_t(MemoryLayout<mach_task_basic_info>.size / MemoryLayout<natural_t>.size)
    let result = withUnsafeMutablePointer(to: &info) {
        $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
            task_info(mach_task_self_, task_flavor_t(MACH_TASK_BASIC_INFO), $0, &count)
        }
    }
    return result == KERN_SUCCESS ? UInt64(info.resident_size) : nil
}
let input = try JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))) as! [String: Any]
let cases = input["cases"] as! [[String: Any]]
let schemes: [NLTagScheme] = [.lexicalClass, .nameType, .nameTypeOrLexicalClass, .lemma]
let available = NLTagger.availableTagSchemes(for: .word, language: .english)
var results: [[String: Any]] = []
for c in cases {
    let start = DispatchTime.now().uptimeNanoseconds
    let before = residentBytes()
    let text = c["text"] as! String
    let tagger = NLTagger(tagSchemes: schemes)
    tagger.string = text
    tagger.setLanguage(.english, range: text.startIndex..<text.endIndex)
    var observations: [[String: Any]] = []
    for scheme in schemes {
        if !available.contains(scheme) {
            observations.append(["scheme": scheme.rawValue, "abstention": "scheme unavailable for English word unit"])
            continue
        }
        tagger.enumerateTags(in: text.startIndex..<text.endIndex, unit: .word, scheme: scheme, options: []) { tag, range in
            let ns = NSRange(range, in: text)
            let (hypotheses, hypothesisRange) = tagger.tagHypotheses(at: range.lowerBound, unit: .word, scheme: scheme, maximumCount: 3)
            let ranked = hypotheses.map { ["tag": $0.key, "confidence": $0.value] as [String: Any] }.sorted { ($0["confidence"] as! Double) > ($1["confidence"] as! Double) }
            observations.append(["scheme": scheme.rawValue, "utf16_start": ns.location, "utf16_length": ns.length, "substring": String(text[range]), "tag": tag.map { $0.rawValue as Any } ?? NSNull(), "abstention": tag == nil ? "no tag returned" : NSNull(), "hypotheses": ranked, "hypothesis_utf16_start": NSRange(hypothesisRange, in: text).location, "hypothesis_utf16_length": NSRange(hypothesisRange, in: text).length, "confidence": tag.flatMap { hypotheses[$0.rawValue] }.map { $0 as Any } ?? NSNull(), "confidence_basis": "NLTagger.tagHypotheses; null if selected tag absent"])
            return true
        }
    }
    var usage = rusage(); getrusage(RUSAGE_SELF, &usage)
    results.append(["id": c["id"]!, "text": text, "utf16_length": text.utf16.count, "observations": observations, "elapsed_nanoseconds": DispatchTime.now().uptimeNanoseconds - start, "process_rss_before_bytes": before.map { $0 as Any } ?? NSNull(), "process_rss_after_bytes": residentBytes().map { $0 as Any } ?? NSNull(), "process_lifetime_peak_rss_bytes": usage.ru_maxrss])
}
let output: [String: Any] = ["schema": "vipi.native-source-annotations-output.1", "platform": "macOS desktop VM", "os": ProcessInfo.processInfo.operatingSystemVersionString, "available_schemes": available.map { $0.rawValue }, "cases": results, "limits": "Annotations are not sense authority. Timing includes tagger construction, tagging and hypotheses. RSS is process-wide, peak cumulative; not isolated per-case allocation."]
let data = try JSONSerialization.data(withJSONObject: output, options: [.prettyPrinted, .sortedKeys])
try data.write(to: URL(fileURLWithPath: CommandLine.arguments[2]), options: .atomic)
