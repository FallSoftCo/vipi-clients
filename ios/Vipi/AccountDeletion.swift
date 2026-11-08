import Foundation
import Observation
import Security

struct DeletionRecord: Codable {
    enum Phase: String, Codable { case prepared, requested, completed }
    let account: UUID
    let userID: String
    let secret: String
    let createdAt: Date
    var phase = Phase.prepared
    var localErased = false
}
struct DeletionReply: Decodable { let account_id: UUID; let status: String }
@MainActor protocol DeletionStore {
    func load() throws -> DeletionRecord?
    func save(_ record: DeletionRecord) throws
    func remove() throws
}
@MainActor struct KeychainDeletionStore: DeletionStore {
    func load() throws -> DeletionRecord? { try KeychainStore.read(account: "account-deletion").map { try JSONDecoder().decode(DeletionRecord.self, from: $0) } }
    func save(_ record: DeletionRecord) throws { try KeychainStore.save(JSONEncoder().encode(record), account: "account-deletion") }
    func remove() throws { try KeychainStore.deleteChecked(account: "account-deletion") }
}
@MainActor protocol DeletionTransport {
    func submit(_ record: DeletionRecord) async throws -> DeletionReply
    func status(_ record: DeletionRecord) async throws -> DeletionReply
}
private final class NoDeletionRedirects: NSObject, URLSessionTaskDelegate, Sendable {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping @Sendable (URLRequest?) -> Void) { completionHandler(nil) }
}
@MainActor final class AccountDeletionService: DeletionTransport {
    let authentication: AuthenticationManager
    private let http: URLSession
    init(authentication: AuthenticationManager) {
        self.authentication = authentication
        let config = URLSessionConfiguration.ephemeral
        config.urlCache = nil; config.httpCookieStorage = nil; config.timeoutIntervalForRequest = 20; config.timeoutIntervalForResource = 25
        http = URLSession(configuration: config, delegate: NoDeletionRedirects(), delegateQueue: nil)
    }
    deinit { http.invalidateAndCancel() }
    func submit(_ record: DeletionRecord) async throws -> DeletionReply {
        let body = try JSONSerialization.data(withJSONObject: ["account_id": record.account.uuidString.lowercased(), "receipt_secret": record.secret])
        return try await ServiceClient(authentication: authentication, userID: record.userID).request("DELETE", "/v1/me", body: body)
    }
    func status(_ record: DeletionRecord) async throws -> DeletionReply {
        var request = URLRequest(url: URL(string: "https://api.mambovipi.app/v1/account-deletions/" + record.account.uuidString.lowercased())!)
        request.setValue("Deletion " + record.secret, forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        let (bytes, response) = try await http.bytes(for: request)
        guard let response = response as? HTTPURLResponse, response.expectedContentLength <= 4096 else { throw ServiceFailure(status: 0, code: "invalid_response") }
        var data = Data()
        for try await byte in bytes { guard data.count < 4096 else { throw ServiceFailure(status: 0, code: "invalid_response") }; data.append(byte) }
        guard response.statusCode == 200 else { throw ServiceFailure(status: response.statusCode, code: "deletion_status_unavailable") }
        return try JSONDecoder().decode(DeletionReply.self, from: data)
    }
}

/// Save the capability before DELETE. Confirmed server progress is durable before
/// erasing local data, and no network exception is interpreted as non-deletion.
@MainActor @Observable final class AccountDeletion {
    private(set) var pending: DeletionRecord?
    private(set) var busy = false
    private(set) var loadFailed = false
    private(set) var needsSignIn = false
    var notice: String?
    var active: Bool { pending != nil || loadFailed }
    private let store: any DeletionStore
    private let service: any DeletionTransport
    private let erase: (DeletionRecord) throws -> Void
    private let signOut: (String) throws -> Void
    init(store: any DeletionStore, service: any DeletionTransport,
         erase: @escaping (DeletionRecord) throws -> Void, signOut: @escaping (String) throws -> Void) {
        self.store = store; self.service = service; self.erase = erase; self.signOut = signOut
        do { pending = try store.load() } catch { loadFailed = true; notice = "Your deletion receipt couldn’t be opened. Close and reopen Vipi to try again." }
    }
    convenience init(authentication: AuthenticationManager) {
        self.init(store: KeychainDeletionStore(), service: AccountDeletionService(authentication: authentication), erase: Self.eraseLocal) { userID in
            try authentication.eraseLocalSession(for: userID)
        }
    }
    static func eraseLocal(_ record: DeletionRecord) throws {
        // The chat coordinator must be closed before entering this operation.
        try KeychainStore.deleteChecked(account: "messages-" + record.account.uuidString.lowercased())
        let folder = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Messages").appendingPathComponent(record.account.uuidString.lowercased())
        if FileManager.default.fileExists(atPath: folder.path) { try FileManager.default.removeItem(at: folder) }
        // These are private, temporary encrypted copies, not files the user
        // chose to save through Files. The coordinator is already closed.
        let temporaryHistory = folder.deletingLastPathComponent().deletingLastPathComponent().appendingPathComponent("HistoryFiles")
        if FileManager.default.fileExists(atPath: temporaryHistory.path) { try FileManager.default.removeItem(at: temporaryHistory) }
        // Rendered message audio contains the same private conversation content
        // as the vault. Public downloaded voices and language packs are separate.
        let speech = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("vipi-speech", isDirectory: true)
        if FileManager.default.fileExists(atPath: speech.path) { try FileManager.default.removeItem(at: speech) }
        try KeychainStore.deleteChecked(account: "profile-" + record.userID)
    }
    func begin(account: UUID, userID: String, closeChat: () throws -> Void) throws {
        guard !active, !busy else { throw ServiceFailure(status: 0, code: "deletion_in_progress") }
        var bytes = [UInt8](repeating: 0, count: 32)
        guard SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes) == errSecSuccess else { throw MessageVault.Failure.invalidRecord }
        let secret = Data(bytes).base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "")
        try closeChat()
        let record = DeletionRecord(account: account, userID: userID, secret: secret, createdAt: Date())
        try store.save(record); pending = record; notice = nil
    }
    private func accept(_ reply: DeletionReply, for record: DeletionRecord) throws {
        guard reply.account_id == record.account, ["deletion_requested", "deleted"].contains(reply.status) else { throw ServiceFailure(status: 0, code: "invalid_deletion_response") }
        var next = record; next.phase = reply.status == "deleted" ? .completed : .requested
        try store.save(next); pending = next
    }
    private func eraseIfConfirmed() throws {
        guard var record = pending, record.phase != .prepared else { return }
        if !record.localErased {
            try erase(record); try signOut(record.userID); record.localErased = true
            try store.save(record); pending = record
        } else { try signOut(record.userID) }
    }
    func resume() async {
        guard !busy, pending != nil else { return }
        busy = true; notice = nil; needsSignIn = false
        defer { busy = false }
        do {
            try eraseIfConfirmed()
            let record = pending!
            if record.phase == .completed { return }
            do { try accept(await service.status(record), for: record) }
            catch let error as ServiceFailure where error.status == 404 && record.phase == .prepared && Date().timeIntervalSince(record.createdAt) < 7 * 86400 {
                try accept(await service.submit(record), for: record)
            }
            try eraseIfConfirmed()
        } catch is CancellationError { notice = "The request was interrupted. Check its status to continue." }
        catch let error as ServiceFailure where error.code == "recent_sign_in_required" || error.code == "sign_in_required" {
            needsSignIn = true; notice = "Sign in to the same account once more to confirm it’s you, then continue."
        } catch is AuthenticationManager.SessionFailure {
            needsSignIn = true; notice = "Sign in to the same account once more to continue."
        } catch {
            notice = pending?.phase == .prepared ? "We couldn’t confirm your request. Check your connection and try again. You won’t need to start over." : "Your request is saved. We couldn’t check completion. Please try again."
        }
    }
    func finish() {
        guard !busy, let record = pending, record.phase == .completed, record.localErased else { return }
        do { try store.remove(); pending = nil; notice = nil } catch { notice = "The completion receipt couldn’t be cleared. Please try again." }
    }
}
