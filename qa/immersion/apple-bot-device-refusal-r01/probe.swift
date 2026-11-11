import Foundation
import Security
import Observation
import SwiftUI
final class MessageVault {
 enum Failure: Error { case invalidRecord }
 var values: [String: Data] = [:]
 func transaction<T>(_ f: () throws -> T) rethrows -> T { try f() }
 func get(_ kind: String, _ id: String) throws -> Data? { values[kind+":"+id] }
 func put(_ kind: String, _ id: String, _ data: Data) throws { values[kind+":"+id] = data }
 func remove(_ kind: String, _ id: String) throws { values.removeValue(forKey:kind+":"+id) }
 func ids(_ kind: String) throws -> [String] { values.keys.filter{$0.hasPrefix(kind+":")}.map{String($0.dropFirst(kind.count+1))} }
 func pageIDs(_ kind: String, prefix: String, before: String?, limit: Int) throws -> [String] {
  try ids(kind).filter{$0.hasPrefix(prefix) && (before == nil || $0 < before!)}.sorted().suffix(limit).map{$0}
 }
}
final class VocabularyFamiliarityStore { init(vault: MessageVault) {} }
struct DeviceCredential: Codable, Sendable {
    let id: UUID; let secret: String
    static func load(vault: MessageVault) throws -> Self {
        try vault.transaction {
            if let data = try vault.get("local", "service-device") { return try JSONDecoder().decode(Self.self, from: data) }
            let result = try generate()
            try vault.put("local", "service-device", JSONEncoder().encode(result))
            return result
        }
    }
    static func registered(vault: MessageVault) throws -> Self {
        try vault.transaction {
            guard let data = try vault.get("local", "service-device") else {
                throw ServiceFailure(status: 0, code: "device_registration_required")
            }
            let value = try JSONDecoder().decode(Self.self, from: data)
            guard try vault.get("local", "registered-device") == Data(value.id.uuidString.lowercased().utf8) else {
                throw ServiceFailure(status: 0, code: "device_registration_required")
            }
            return value
        }
    }
    static func generate() throws -> Self {
            var bytes = [UInt8](repeating: 0, count: 32)
            guard SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes) == errSecSuccess else { throw MessageVault.Failure.invalidRecord }
            let secret = Data(bytes).base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "")
            return Self(id: UUID(), secret: secret)
    }

}

struct ServiceFailure: Error { let status: Int; let code: String }
@MainActor protocol ChatTransport {
    func request<T: Decodable>(_ method: String, _ path: String, body: Data?, device: DeviceCredential?, query: [String: String], as type: T.Type) async throws -> T
}
extension ChatTransport {
    func request<T: Decodable>(_ method: String, _ path: String, body: Data? = nil, device: DeviceCredential? = nil, query: [String: String] = [:]) async throws -> T {
        try await request(method, path, body: body, device: device, query: query, as: T.self)
    }
}

struct BotAllowance: Decodable, Sendable {
    let available: Bool
    let service_ready: Bool
    let remaining_replies: Int
    let monthly_replies: Int
    let resets_at: String
    let max_context_bytes: Int
}

import Foundation
import Observation
import SwiftUI

struct BotMessage: Codable, Identifiable {
    let id: UUID
    let role: String
    let text: String
    let createdAt: Date
    var state: String
    var requestID: UUID? = nil
    var key: String { String(format: "%020lld", Int64(createdAt.timeIntervalSince1970 * 1000)) + "-" + id.uuidString.lowercased() }
}

/// This storage namespace and request builder contain only the vBot thread.
/// The friend-message journal is never an input to response generation.
@MainActor @Observable final class BotSession {
    private let api: any ChatTransport
    private let vault: MessageVault
    let familiarity: VocabularyFamiliarityStore
    private var closed = false
    private(set) var messages: [BotMessage] = []
    private(set) var consent = false
    private(set) var busy = false
    private(set) var allowance: BotAllowance?
    private(set) var earlierAvailable = false
    var notice: String?
    var draft = ""
    init(api: any ChatTransport, vault: MessageVault) throws {
        self.api = api; self.vault = vault
        self.familiarity = VocabularyFamiliarityStore(vault: vault)
        try vault.transaction {
            consent = try vault.get("bot-local", "consent") == Data("deepseek-v1".utf8)
            draft = try vault.get("bot-local", "draft").flatMap { String(data: $0, encoding: .utf8) } ?? ""
        }
        try loadEarlier()
    }
    func close() { closed = true }
    func loadEarlier() throws {
        let before = messages.first?.key
        let page = try vault.transaction {
            try vault.pageIDs("bot-message", prefix: "0", before: before, limit: 50).compactMap { key -> BotMessage? in
                guard let data = try vault.get("bot-message", key) else { return nil }
                var message = try JSONDecoder().decode(BotMessage.self, from: data)
                if message.state == "sending" { message.state = "unconfirmed" }
                return message
            }
        }
        earlierAvailable = page.count == 50
        messages = (page + messages).sorted { $0.key < $1.key }
    }
    func saveDraft() {
        do { try vault.transaction { try vault.put("bot-local", "draft", Data(draft.utf8)) } }
        catch { notice = "This draft couldn’t be saved. Keep this conversation open and try again." }
    }
    func setConsent(_ value: Bool) throws {
        guard !busy else { return }
        try vault.transaction {
            if value { try vault.put("bot-local", "consent", Data("deepseek-v1".utf8)) }
            else { try vault.remove("bot-local", "consent") }
        }
        consent = value
    }
    func clear() throws {
        guard !busy else { return }
        try vault.transaction { for id in try vault.ids("bot-message") { try vault.remove("bot-message", id) } }
        messages = []; earlierAvailable = false
    }
    func refresh() async {
        do {
            let value: BotAllowance = try await api.request("GET", "/v1/bot/allowance")
            guard !closed else { return }; allowance = value
        } catch { if !closed { allowance = nil; notice = "Couldn’t check your Bot mini allowance. Try again." } }
    }
    var canSend: Bool {
        !closed && !busy && consent && allowance?.available == true && (allowance?.remaining_replies ?? 0) > 0 &&
        !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && draft.utf8.count <= min(8192, allowance?.max_context_bytes ?? 0)
    }
    struct Context: Codable { let role: String; let content: String }
    static func context(history: [BotMessage], newText: String, maximumBytes: Int) -> [Context]? {
        guard !newText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              newText.utf8.count <= min(8192, maximumBytes) else { return nil }
        var values = history.filter { $0.state == "complete" && ["user", "assistant"].contains($0.role) }
            .suffix(11).map { Context(role: $0.role, content: $0.text) }
        values.append(Context(role: "user", content: newText))
        while values.reduce(0, { $0 + $1.content.utf8.count }) > min(8192, maximumBytes) { values.removeFirst() }
        return values
    }
    func send() async {
        guard canSend, let context = Self.context(history: messages, newText: draft, maximumBytes: allowance?.max_context_bytes ?? 0) else { return }
        busy = true; notice = nil
        defer { busy = false }
        let device: DeviceCredential
        do { device = try DeviceCredential.registered(vault: vault) }
        catch {
            notice = "Reconnect this account before sending to vBot. Your draft is still here."
            return
        }
        var outgoing = BotMessage(id: UUID(), role: "user", text: draft, createdAt: Date(), state: "sending")
        struct Request: Encodable { let request_id: UUID; let consent_version: String; let messages: [Context] }
        struct Reply: Decodable { let request_id: UUID; let reply: String; let allowance: BotAllowance }
        do {
            try vault.transaction {
                try vault.put("bot-message", outgoing.key, JSONEncoder().encode(outgoing))
                try vault.remove("bot-local", "draft")
            }
            messages.append(outgoing); draft = ""
        } catch { notice = "Your message couldn’t be saved. Please try again."; return }
        do {
            let body = try JSONEncoder().encode(Request(request_id: outgoing.id, consent_version: "deepseek-v1", messages: context))
            let reply: Reply = try await api.request("POST", "/v1/bot/messages", body: body, device: device)
            guard reply.request_id == outgoing.id, !reply.reply.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  reply.reply.utf8.count <= 16384 else { throw ServiceFailure(status: 0, code: "invalid_bot_reply") }
            // Complete the local record even if navigation closed the view
            // while the request was in flight. No follow-up request is sent.
            outgoing.state = "complete"
            var incoming = BotMessage(id: UUID(), role: "assistant", text: reply.reply, createdAt: Date(), state: "complete")
            incoming.requestID = outgoing.id
            try vault.transaction {
                try vault.put("bot-message", outgoing.key, JSONEncoder().encode(outgoing))
                try vault.put("bot-message", incoming.key, JSONEncoder().encode(incoming))
            }
            if let index = messages.firstIndex(where: { $0.id == outgoing.id }) { messages[index] = outgoing }
            messages.append(incoming); allowance = reply.allowance
        } catch {
            outgoing.state = (error as? ServiceFailure)?.code == "device_revoked" ? "rejected" : "unconfirmed"
            try? vault.transaction { try vault.put("bot-message", outgoing.key, JSONEncoder().encode(outgoing)) }
            if let index = messages.firstIndex(where: { $0.id == outgoing.id }) { messages[index] = outgoing }
            notice = Self.explanation(error)
            // Never retry a potentially consumed response-generation request.
            if !closed { await refresh() }
        }
    }
    static func reportExcerpt(_ text: String) -> String {
        var result = ""
        for character in text {
            guard result.utf8.count + String(character).utf8.count <= 4000 else { break }
            result.append(character)
        }
        return result
    }
    func report(_ message: BotMessage, reason: String) async throws {
        guard !closed, message.role == "assistant", let request = message.requestID,
              ["harmful", "inaccurate", "other"].contains(reason) else { throw ServiceFailure(status: 0, code: "invalid_report") }
        struct Report: Encodable { let request_id: UUID; let reason: String; let selected_reply: String }
        struct Result: Decodable { let reported: Bool }
        let body = try JSONEncoder().encode(Report(request_id: request, reason: reason, selected_reply: Self.reportExcerpt(message.text)))
        let device = try DeviceCredential.registered(vault: vault)
        let result: Result = try await api.request("POST", "/v1/bot/reports", body: body, device: device)
        guard result.reported else { throw ServiceFailure(status: 0, code: "report_unconfirmed") }
    }
    private static func explanation(_ error: Error) -> String {
        if let error = error as? ServiceFailure {
            if error.code == "device_revoked" { return "Reconnect this account before sending to vBot. This request wasn’t accepted and won’t be resent automatically." }
            if error.code == "monthly_allowance_reached" { return "You’ve used this month’s Bot mini replies. Your allowance refreshes next month." }
            if ["base_subscription_required", "bot_subscription_required"].contains(error.code) { return "Check your subscriptions to continue this conversation." }
            if ["bot_unavailable", "bot_busy", "bot_temporarily_unavailable"].contains(error.code) { return "vBot is unavailable right now. Your message is saved and won’t be resent automatically." }
        }
        return "We couldn’t confirm vBot’s reply. This message won’t be resent automatically and may have used one reply from your allowance."
    }
}


@MainActor final class FakeTransport: ChatTransport {
 var posts: [(String, DeviceCredential?, Data?)] = []; var fail = false; var refusal: String?
 func request<T: Decodable>(_ method: String, _ path: String, body: Data?, device: DeviceCredential?, query: [String:String], as type: T.Type) async throws -> T {
  let allowance: [String:Any] = ["available":true,"service_ready":true,"remaining_replies":149,"monthly_replies":150,"resets_at":"2026-12-01T00:00:00Z","max_context_bytes":8192]
  var result = allowance
  if method == "POST" {
   posts.append((path,device,body))
   if let refusal { throw ServiceFailure(status:401,code:refusal) }
   if fail { throw URLError(.timedOut) }
   if path == "/v1/bot/messages" {
    let request = try JSONSerialization.jsonObject(with: body!) as! [String:Any]
    result = ["request_id":request["request_id"]!,"reply":"Synthetic reply","allowance":allowance]
   } else { result = ["reported":true] }
  }
  return try JSONDecoder().decode(type,from:JSONSerialization.data(withJSONObject:result))
 }
}
@MainActor func fixture() throws -> (MessageVault,DeviceCredential) {
 let vault=MessageVault(), credential=DeviceCredential(id:UUID(),secret:String(repeating:"x",count:43))
 try vault.put("local","service-device",JSONEncoder().encode(credential))
 try vault.put("local","registered-device",Data(credential.id.uuidString.lowercased().utf8))
 return (vault,credential)
}
@MainActor func run() async throws {
 let (vault,credential)=try fixture();let api=FakeTransport();let session=try BotSession(api:api,vault:vault)
 try vault.put("message","friend",Data("Never include friend content".utf8))
 await session.refresh();try session.setConsent(true);session.draft="Hello";await session.send()
 precondition(api.posts.count==1 && api.posts[0].1?.id==credential.id && api.posts[0].1?.secret==credential.secret)
 precondition(session.messages.count==2 && session.messages.allSatisfy{$0.state=="complete"})
 precondition(!String(decoding:api.posts[0].2!,as:UTF8.self).contains("Never include"))
 try await session.report(session.messages.last!,reason:"inaccurate")
 precondition(api.posts.count==2 && api.posts[1].1?.id==credential.id && api.posts[1].1?.secret==credential.secret)
 let (uncertainVault,uncertainCredential)=try fixture();let failing=FakeTransport();failing.fail=true
 let uncertain=try BotSession(api:failing,vault:uncertainVault);await uncertain.refresh();try uncertain.setConsent(true);uncertain.draft="One request";await uncertain.send()
 precondition(uncertain.messages.first?.state=="unconfirmed" && failing.posts.count==1 && failing.posts[0].1?.id==uncertainCredential.id)
 let reopened=try BotSession(api:failing,vault:uncertainVault);await reopened.refresh();await reopened.send()
 precondition(reopened.messages.first?.state=="unconfirmed" && failing.posts.count==1)
 for code in ["device_revoked", "unknown_failure"] {
  let (v,_)=try fixture();let t=FakeTransport();t.refusal=code
  let s=try BotSession(api:t,vault:v);await s.refresh();try s.setConsent(true);s.draft="One request";await s.send()
  let expected = code == "device_revoked" ? "rejected" : "unconfirmed"
  precondition(s.messages.first?.state==expected && s.draft.isEmpty)
  precondition((s.notice?.contains("wasn’t accepted") == true) == (code == "device_revoked"))
  let reopened=try BotSession(api:t,vault:v);await reopened.refresh();await reopened.send()
  precondition(reopened.messages.first?.state==expected && t.posts.count==1)
 }
 for failure in ["missing","unregistered","replaced","malformed"] {
  let (v,_)=try fixture();let t=FakeTransport();let s=try BotSession(api:t,vault:v);await s.refresh();try s.setConsent(true);s.draft="Keep draft";s.saveDraft()
  if failure=="missing" {try v.remove("local","service-device")}
  if failure=="unregistered" {try v.remove("local","registered-device")}
  if failure=="replaced" {try v.put("local","registered-device",Data(UUID().uuidString.lowercased().utf8))}
  if failure=="malformed" {try v.put("local","service-device",Data("broken".utf8))}
  await s.send();precondition(t.posts.isEmpty && s.messages.isEmpty && s.draft=="Keep draft")
  let again=try BotSession(api:t,vault:v);precondition(again.draft=="Keep draft")
 }
 print("PASS: exact device_revoked rejected; unknown failure and timeout unconfirmed; no replay; actual BotSession/DeviceCredential send+report credential, no automatic resend, four pre-send credential failures preserve draft; stub vault+transport only")
}
try await run()
