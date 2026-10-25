#if DEBUG
import Foundation

/// Synthetic process-termination probe; no real accounts or messages are used.
enum PersistenceProbe {
    private enum Failure: Error { case timeout, invalidProbe, rollbackFailed }
    static func startIfRequested() {
        let arguments = ProcessInfo.processInfo.arguments
        guard arguments.contains("-vipi-storage-stage") || arguments.contains("-vipi-storage-verify") else { return }
        let stage = arguments.contains("-vipi-storage-stage")
        DispatchQueue.global(qos: .utility).async {
            let directory = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            let probe = directory.appendingPathComponent("storage-crash-probe.json")
            let armed = directory.appendingPathComponent("storage-crash-armed")
            let receipt = directory.appendingPathComponent("storage-crash-receipt.json")
            do {
                if stage {
                    try? FileManager.default.removeItem(at: armed)
                    try? FileManager.default.removeItem(at: receipt)
                    let account = UUID()
                    try JSONSerialization.data(withJSONObject: ["purpose": "SYNTHETIC SQLITE PROCESS TERMINATION", "account": account.uuidString]).write(to: probe, options: .atomic)
                    let vault = try MessageVault(account: account)
                    try vault.transaction { try vault.put("crash-test", "existing", Data("committed".utf8)) }
                    try vault.transaction {
                        try vault.put("crash-test", "existing", Data("uncommitted".utf8))
                        try vault.put("crash-test", "new", Data("must roll back".utf8))
                        try Data("armed".utf8).write(to: armed, options: .atomic)
                        let handle = try FileHandle(forWritingTo: armed); try handle.synchronize(); try handle.close()
                        Thread.sleep(forTimeInterval: 60)
                        throw Failure.timeout
                    }
                } else {
                    let values = try JSONSerialization.jsonObject(with: Data(contentsOf: probe)) as? [String: String]
                    guard values?["purpose"] == "SYNTHETIC SQLITE PROCESS TERMINATION", let text = values?["account"], let account = UUID(uuidString: text) else { throw Failure.invalidProbe }
                    let vault = try MessageVault(account: account)
                    try vault.transaction {
                        guard try vault.get("crash-test", "existing") == Data("committed".utf8), try vault.get("crash-test", "new") == nil else { throw Failure.rollbackFailed }
                    }
                    try JSONSerialization.data(withJSONObject: ["status": "passed", "scope": "abrupt process termination rolls back uncommitted native SQLite records"]).write(to: receipt, options: .atomic)
                }
            } catch { try? JSONSerialization.data(withJSONObject: ["status": "failed", "error": String(describing: error)]).write(to: receipt, options: .atomic) }
        }
    }
}
#endif
