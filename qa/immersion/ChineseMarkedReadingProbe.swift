import Foundation

@main struct ChineseMarkedReadingProbe {
    struct Fixture: Codable { let source: String; let expected: String? }
    static func main() throws {
        let args = CommandLine.arguments
        guard args.count == 4 else { fatalError("DATA FIXTURES OUTPUT") }
        let reader = try ChineseFullReading(data: Data(contentsOf: URL(fileURLWithPath: args[1])))
        let fixtures = try JSONDecoder().decode([Fixture].self, from: Data(contentsOf: URL(fileURLWithPath: args[2])))
        var rows: [[String: Any]] = []
        for fixture in fixtures {
            let result = try reader.resolve(fixture.source)
            precondition(result.reading == fixture.expected, "\(fixture.source): \(result.reading ?? "nil") != \(fixture.expected ?? "nil")")
            precondition(result.pieces.map(\.source).joined() == fixture.source)
            precondition(result.pieces.filter(\.protected).allSatisfy { $0.source == $0.reading && !$0.converted })
            let warm = try reader.resolve(fixture.source)
            precondition(warm.reading == result.reading)
            rows.append(["source":fixture.source,"reading":result.reading as Any? ?? NSNull(),"source_partition":true,"warm_identical":true])
        }
        let long = String(repeating: "银行还款。", count: 3276) + "银行还款"
        let start = Date()
        let full = try reader.resolve(long)
        precondition(full.reading?.hasPrefix("yínháng") == true && full.pieces.map(\.source).joined() == long)
        do { _ = try reader.resolve(String(repeating:"银",count:16385)); fatalError("accepted oversized input") } catch ChineseFullReading.Invalid.input { }
        let report: [String: Any] = ["schema":"vipi-marked-chinese-regression-1","platform":"native macOS Swift CLI; not iOS render evidence","data_sha256":ChineseFullReading.dataSHA256,"policy":ChineseFullReading.policy,"cases":rows,"max_input_utf16":long.utf16.count,"max_input_ms":Date().timeIntervalSince(start)*1000,"original_script_audio_authority":true]
        try JSONSerialization.data(withJSONObject:report,options:[.prettyPrinted,.sortedKeys,.withoutEscapingSlashes]).write(to:URL(fileURLWithPath:args[3]),options:.withoutOverwriting)
    }
}
