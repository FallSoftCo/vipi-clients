import Foundation
import Translation
@main struct Availability {
 @MainActor static func main() async throws {
 let data = try Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))
 let p = try JSONDecoder().decode(LabProtocol.self, from: data)
 var rows: [[String: String]] = []
 for strategy in ["lowLatency", "platformDefault"] {
 let checker = strategy == "lowLatency" ? LanguageAvailability(preferredStrategy: .lowLatency) : LanguageAvailability()
 for c in p.cases {
 let status = await checker.status(from: .init(identifier:c.source), to:.init(identifier:c.target))
 rows.append(["source":c.source,"target":c.target,"strategy":strategy,"status":String(describing:status)])
 try JSONSerialization.data(withJSONObject:["os":ProcessInfo.processInfo.operatingSystemVersionString,"rows":rows],options:[.prettyPrinted,.sortedKeys]).write(to:URL(fileURLWithPath:CommandLine.arguments[2]),options:.atomic)
 }
 }
 }
}
