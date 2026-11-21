#if DEBUG
import SwiftUI
import Observation

/// Explicit fresh local authentication. No native account token is read,
/// refreshed, replaced, or sent to this loopback-only test transport.
@MainActor private final class NativeReadTransport:ChatTransport {
    private let endpoint:URL
    private let token:String
    private let http = URLSession(configuration:.ephemeral,delegate:NoRedirects(),delegateQueue:nil)
    private final class NoRedirects:NSObject,URLSessionTaskDelegate,Sendable {
        func urlSession(_ session:URLSession,task:URLSessionTask,willPerformHTTPRedirection response:HTTPURLResponse,newRequest request:URLRequest,completionHandler:@escaping @Sendable (URLRequest?)->Void) { completionHandler(nil) }
    }
    init(endpoint:URL,token:String) throws {
        guard endpoint.scheme == "http",endpoint.host == "127.0.0.1",endpoint.port == 48955,
              endpoint.user == nil,endpoint.password == nil,endpoint.query == nil,endpoint.fragment == nil,
              endpoint.path.isEmpty || endpoint.path == "/",token.count > 100 else { throw ServiceFailure(status:0,code:"owned_loopback_required") }
        self.endpoint = endpoint; self.token = token
    }
    func request<T:Decodable>(_ method:String,_ path:String,body:Data?,device:DeviceCredential?,query:[String:String],as type:T.Type) async throws -> T {
        guard path.hasPrefix("/v1/"),!path.contains(".."),!path.contains("?"),!path.contains("#") else { throw ServiceFailure(status:0,code:"invalid_local_path") }
        var parts = URLComponents(url:endpoint,resolvingAgainstBaseURL:false)!
        parts.path = path; parts.queryItems = query.sorted{$0.key < $1.key}.map{URLQueryItem(name:$0.key,value:$0.value)}
        var request = URLRequest(url:parts.url!); request.httpMethod = method; request.httpBody = body
        request.setValue("Bearer "+token,forHTTPHeaderField:"Authorization"); request.setValue("application/json",forHTTPHeaderField:"Content-Type")
        if let device { request.setValue(device.id.uuidString.lowercased(),forHTTPHeaderField:"X-Vipi-Device-ID"); request.setValue(device.secret,forHTTPHeaderField:"X-Vipi-Device-Secret") }
        let (data,response) = try await http.data(for:request),status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200...299).contains(status),data.count <= 12_000_000 else { throw ServiceFailure(status:status,code:"local_read_fixture_request_failed") }
        return try JSONDecoder().decode(type,from:data)
    }
}

@MainActor @Observable private final class NativeReadQualification {
    private struct Identity:Decodable { let subject:String;let username:String;let access_token:String }
    private struct Configuration:Decodable { let run:String;let endpoint:URL;let holder:Identity;let peer:Identity }
    private struct Owner:Codable { let run:String;let accounts:[UUID];let subjects:[String] }
    private static var directory:URL { FileManager.default.urls(for:.documentDirectory,in:.userDomainMask)[0] }
    private static var ownerFile:URL { directory.appendingPathComponent("native-read-owner.json") }
    var holder:ChatSession?
    private var peer:ChatSession?
    private var peerAPI:NativeReadTransport?
    private var owner:Owner?
    var phase = "preparing"
    var busy = false
    var read:[String] = []
    var outgoing:[String] = []
    var hiddenID = ""
    var error = ""
    var proof:String {
        let value:[String:Any] = ["phase":phase,"read":read,"outgoing":outgoing,"hidden_id":hiddenID,"error":error,"independent_local_authentication":true,"normal_backend_http":true,"scripted_read_acknowledgements":false]
        return String(data:(try? JSONSerialization.data(withJSONObject:value,options:.sortedKeys)) ?? Data(),encoding:.utf8) ?? "{}"
    }
    static func cleanup() throws {
        guard Bundle.main.bundleIdentifier == "co.fallsoft.vipi.uxqa" else { throw ServiceFailure(status:0,code:"owned_simulator_required") }
        if FileManager.default.fileExists(atPath:ownerFile.path) {
            let owner = try JSONDecoder().decode(Owner.self,from:Data(contentsOf:ownerFile))
            guard owner.run.hasPrefix("native-read-"),owner.accounts.count <= 2,owner.subjects.count == 2,
                  owner.subjects.allSatisfy({$0.hasPrefix("user_localpair_")}) else { throw ServiceFailure(status:0,code:"preserve_unknown_read_fixture") }
            for subject in owner.subjects { try KeychainStore.deleteChecked(account:"profile-"+subject) }
            for id in owner.accounts {
                try KeychainStore.deleteChecked(account:"messages-"+id.uuidString.lowercased())
                try KeychainStore.deleteChecked(account:"messages-initializing-"+id.uuidString.lowercased())
                try KeychainStore.deleteChecked(account:"notification-store-location-"+id.uuidString.lowercased())
                for root in [NotificationAccess.legacyRoot, NotificationAccess.root].compactMap({ $0 }) {
                    let folder = root.appendingPathComponent(id.uuidString.lowercased())
                    if FileManager.default.fileExists(atPath:folder.path) { try FileManager.default.removeItem(at:folder) }
                }
            }
            try FileManager.default.removeItem(at:ownerFile)
        }
        let config = directory.appendingPathComponent("native-read-config.json")
        if FileManager.default.fileExists(atPath:config.path) { try FileManager.default.removeItem(at:config) }
    }
    func prepare() async {
        guard !busy,holder == nil else { return }; busy = true; defer { busy = false }
        do {
            guard Bundle.main.bundleIdentifier == "co.fallsoft.vipi.uxqa",!FileManager.default.fileExists(atPath:Self.ownerFile.path) else { throw ServiceFailure(status:0,code:"fresh_owned_read_fixture_required") }
            let file = Self.directory.appendingPathComponent("native-read-config.json"),config = try JSONDecoder().decode(Configuration.self,from:Data(contentsOf:file))
            guard config.run.hasPrefix("native-read-"),config.holder.subject != config.peer.subject,
                  [config.holder,config.peer].allSatisfy({$0.subject.hasPrefix("user_localpair_") && $0.username.hasPrefix("vqa_")}) else { throw ServiceFailure(status:0,code:"fresh_local_identities_required") }
            let holderAPI = try NativeReadTransport(endpoint:config.endpoint,token:config.holder.access_token),peerAPI = try NativeReadTransport(endpoint:config.endpoint,token:config.peer.access_token)
            // Record ownership before any keychain/vault creation, so even an
            // interrupted setup retains exact bounded cleanup authority.
            var record = Owner(run:config.run,accounts:[],subjects:[config.holder.subject,config.peer.subject])
            try JSONEncoder().encode(record).write(to:Self.ownerFile,options:.atomic)
            let holder = try ChatSession(api:holderAPI,userID:config.holder.subject),peer = try ChatSession(api:peerAPI,userID:config.peer.subject)
            self.holder = holder; self.peer = peer; self.peerAPI = peerAPI
            await holder.createProfile(username:config.holder.username,name:"Local Holder")
            guard holder.ready,let holderID = holder.profile?.id else { throw ServiceFailure(status:0,code:"holder_profile_not_ready") }
            record = Owner(run:record.run,accounts:[holderID],subjects:record.subjects); try JSONEncoder().encode(record).write(to:Self.ownerFile,options:.atomic)
            await peer.createProfile(username:config.peer.username,name:"Reachable Local Peer")
            guard peer.ready,let peerID = peer.profile?.id else { throw ServiceFailure(status:0,code:"peer_profile_not_ready") }
            record = Owner(run:record.run,accounts:[holderID,peerID],subjects:record.subjects); self.owner = record
            try JSONEncoder().encode(record).write(to:Self.ownerFile,options:.atomic); try FileManager.default.removeItem(at:file)
            _ = try await holder.find(config.peer.username); _ = try await peer.find(config.holder.username)
            try peer.send("The visible reply is really encrypted and acknowledged.",peer:holderID)
            await peer.synchronize(); await holder.synchronize(); await probe()
            phase = "ready"
        } catch { fail(error) }
    }
    private func fail(_ value:Error) { error = (value as? ServiceFailure).map{"\($0.status):\($0.code)"} ?? String(describing:type(of:value)); phase = "failed" }
    func receive(backlog:Bool) async {
        guard !busy,let peer,let holder,let holderID = holder.profile?.id else { return };busy = true; defer { busy = false }
        do {
            let before = Set(try peer.messages(holderID).map(\.id))
            for index in 0..<(backlog ? 24:1) { try peer.send(backlog ? "Earlier private reply \(index+1). We can catch up over coffee tomorrow.":"A new reply while you are reading earlier messages.",peer:holderID) }
            await peer.synchronize(); await holder.synchronize()
            if !backlog { hiddenID = try peer.messages(holderID).first{!before.contains($0.id)}?.id.uuidString.lowercased() ?? "" }
            await probe()
        } catch { fail(error) }
    }
    func probe() async {
        guard let owner,let peer,let peerAPI,owner.accounts.count == 2 else { return }
        do {
            let ids = try peer.messages(owner.accounts[0]).filter(\.outgoing).map(\.id)
            let device = try DeviceCredential.registered(vault:MessageVault(account:owner.accounts[1]))
            let data = try JSONSerialization.data(withJSONObject:["seen":[],"check":ids.map{$0.uuidString.lowercased()}])
            let result:ChatReadReply = try await peerAPI.request("POST","/v1/conversations/"+owner.accounts[0].uuidString.lowercased()+"/receipts",body:data,device:device)
            outgoing = ids.map{$0.uuidString.lowercased()}.sorted();read = result.read.map{$0.uuidString.lowercased()}.sorted()
        } catch { fail(error) }
    }
}

struct NativeReadQualificationView:View {
    @State private var qualification = NativeReadQualification()
    @State private var cleaned = false
    var body:some View {
        Group {
            if cleaned { Text("Owned native read fixture removed").accessibilityIdentifier("native-read-cleaned") }
            else if let chat = qualification.holder,chat.ready { HomeView(chat:chat) }
            else { ProgressView("Preparing independently authenticated local peers") }
        }
        .safeAreaInset(edge:.top,spacing:0) {
            if !cleaned {
                HStack {
                    Button("Backlog") { Task { await qualification.receive(backlog:true) } }.accessibilityIdentifier("native-read-backlog")
                    Button("New reply") { Task { await qualification.receive(backlog:false) } }.accessibilityIdentifier("native-read-new")
                    Button("Probe") { Task { await qualification.probe() } }.accessibilityIdentifier("native-read-probe")
                }.font(.caption).frame(minHeight:44).disabled(qualification.busy)
                Color.clear.frame(height:1).accessibilityElement(children:.ignore).accessibilityLabel("Independent native read evidence").accessibilityIdentifier("native-read-proof|"+qualification.proof)
            }
        }
        .task {
            if ProcessInfo.processInfo.arguments.contains("-vipi-real-visible-read-cleanup") {
                do { try NativeReadQualification.cleanup();cleaned = true } catch { }
            } else { await qualification.prepare() }
        }
    }
}
#endif
