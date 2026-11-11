import pathlib,json,hashlib
out=pathlib.Path(__file__).resolve().parent; r=out.parents[2]/'ios/Vipi'
bot=(r/'BotConversation.swift').read_text().split('struct BotConversationView: View')[0]
service=(r/'ServiceClient.swift').read_text();device=service[service.index('struct DeviceCredential:'):service.index('private struct ServiceErrorBody:')];transport=service[service.index('@MainActor protocol ChatTransport'):service.index('@MainActor final class ServiceClient')]
subscriptions=(r/'Subscriptions.swift').read_text();allowance=subscriptions[subscriptions.index('struct BotAllowance:'):subscriptions.index('@MainActor @Observable final class SubscriptionStore')]
stubs='''import Foundation
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
'''
tests='''
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
'''
(out/'probe.swift').write_text(stubs+device+transport+allowance+bot+tests)
(out/'source-binding.json').write_text(json.dumps({'source_files':{name:hashlib.sha256((r/name).read_bytes()).hexdigest() for name in ['BotConversation.swift','ServiceClient.swift','Subscriptions.swift']},'slices':{'BotMessage_and_BotSession':hashlib.sha256(bot.encode()).hexdigest(),'DeviceCredential_and_ServiceFailure':hashlib.sha256(device.encode()).hexdigest(),'ChatTransport':hashlib.sha256(transport.encode()).hexdigest(),'BotAllowance':hashlib.sha256(allowance.encode()).hexdigest()},'stubs':['MessageVault in-memory namespace semantics, no encryption/keychain/disk proof','VocabularyFamiliarityStore unused property construction','ChatTransport synthetic response/timeout, no network']},indent=2)+'\n')
