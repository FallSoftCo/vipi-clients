import AuthenticationServices
import Foundation
import Observation
import Security
import UIKit
import WorkOS

enum KeychainStore {
    private static let service = "co.fallsoft.vipi.private"
    static func save(_ data: Data, account: String) throws {
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecAttrAccount as String: account]
        let status = SecItemUpdate(query as CFDictionary, [kSecValueData as String: data] as CFDictionary)
        if status == errSecItemNotFound {
            var item = query
            item[kSecValueData as String] = data
            item[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
            let added = SecItemAdd(item as CFDictionary, nil)
            guard added == errSecSuccess else { throw NSError(domain: NSOSStatusErrorDomain, code: Int(added)) }
        } else if status != errSecSuccess { throw NSError(domain: NSOSStatusErrorDomain, code: Int(status)) }
    }
    static func read(account: String) throws -> Data? {
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecAttrAccount as String: account, kSecReturnData as String: true, kSecMatchLimit as String: kSecMatchLimitOne]
        var result: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        if status == errSecItemNotFound { return nil }
        guard status == errSecSuccess else { throw NSError(domain: NSOSStatusErrorDomain, code: Int(status)) }
        return result as? Data
    }
    static func delete(account: String) {
        SecItemDelete([kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecAttrAccount as String: account] as CFDictionary)
    }
    static func deleteChecked(account: String) throws {
        let status = SecItemDelete([kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecAttrAccount as String: account] as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else { throw NSError(domain: NSOSStatusErrorDomain, code: Int(status)) }
    }
}

/// A stored verifier/token may only be sent to an explicitly reviewed client.
enum IdentityAuthority: String, Codable, Sendable, CaseIterable {
    case vipiProduction = "vipi-production", vipiStaging = "vipi-staging", fallsoftVipiProduction = "fallsoft-vipi-production"
    var clientID: String {
        switch self {
        case .vipiProduction: "client_01M6VYVQQ9GWVNS95DFGABXEW9"
        case .vipiStaging: "client_01M5S2CDSQ8F7FEX26G3CY9VS1"
        case .fallsoftVipiProduction: "client_01M7N9Y2DGSJJVT1ZV6TY7DTZ4"
        }
    }
    static var legacy: Self {
        #if DEBUG
        if Bundle.main.object(forInfoDictionaryKey: "WorkOSClientID") as? String == Self.vipiStaging.clientID { return .vipiStaging }
        #endif
        return .vipiProduction
    }
    static func configured(_ clientID: String) throws -> Self {
        guard let value = allCases.first(where: { $0.clientID == clientID }) else { throw URLError(.userAuthenticationRequired) }
        return value
    }
    static func forSignIn(saved: Self?, hasExpectedUser: Bool, configuredClientID: String) throws -> Self {
        if let saved { return saved }
        return try hasExpectedUser ? .legacy : configured(configuredClientID)
    }
    private enum Keys: String, CodingKey { case formatVersion, authority, clientID }
    static func read(from decoder: any Decoder) throws -> Self {
        let record = try decoder.container(keyedBy: Keys.self)
        if !record.contains(.formatVersion) && !record.contains(.authority) && !record.contains(.clientID) { return .legacy }
        guard try record.decode(Int.self, forKey: .formatVersion) == 2 else {
            throw DecodingError.dataCorruptedError(forKey: .formatVersion, in: record, debugDescription: "Unsupported sign-in record")
        }
        let authority = try record.decode(Self.self, forKey: .authority)
        guard try record.decode(String.self, forKey: .clientID) == authority.clientID else {
            throw DecodingError.dataCorruptedError(forKey: .clientID, in: record, debugDescription: "Sign-in authority mismatch")
        }
        return authority
    }
    func write(to encoder: any Encoder) throws {
        var record = encoder.container(keyedBy: Keys.self)
        try record.encode(2, forKey: .formatVersion)
        try record.encode(self, forKey: .authority)
        try record.encode(clientID, forKey: .clientID)
    }
}

struct VipiSession: Codable, Sendable {
    let userID: String
    let accessToken: String
    let refreshToken: String
    let authority: IdentityAuthority
    init(userID: String, accessToken: String, refreshToken: String, authority: IdentityAuthority = .legacy) {
        self.userID = userID; self.accessToken = accessToken; self.refreshToken = refreshToken; self.authority = authority
    }
    func isBound(to authority: IdentityAuthority, subject: String) -> Bool { self.authority == authority && userID == subject }
    private enum Keys: String, CodingKey { case userID, accessToken, refreshToken }
    init(from decoder: any Decoder) throws {
        let record = try decoder.container(keyedBy: Keys.self)
        userID = try record.decode(String.self, forKey: .userID)
        accessToken = try record.decode(String.self, forKey: .accessToken)
        refreshToken = try record.decode(String.self, forKey: .refreshToken)
        authority = try IdentityAuthority.read(from: decoder)
    }
    func encode(to encoder: any Encoder) throws {
        var record = encoder.container(keyedBy: Keys.self)
        try record.encode(userID, forKey: .userID)
        try record.encode(accessToken, forKey: .accessToken)
        try record.encode(refreshToken, forKey: .refreshToken)
        try authority.write(to: encoder)
    }
}
struct PendingSignIn: Codable {
    let state: String; let verifier: String; let createdAt: Date; let expectedUser: String?; let authority: IdentityAuthority
    let link: IdentityLinkIntent?
    init(state: String, verifier: String, createdAt: Date, expectedUser: String?, authority: IdentityAuthority, link: IdentityLinkIntent? = nil) {
        self.state = state; self.verifier = verifier; self.createdAt = createdAt; self.expectedUser = expectedUser; self.authority = authority; self.link = link
    }
    private enum Keys: String, CodingKey { case state, verifier, createdAt, expectedUser, link }
    init(from decoder: any Decoder) throws {
        let record = try decoder.container(keyedBy: Keys.self)
        state = try record.decode(String.self, forKey: .state)
        verifier = try record.decode(String.self, forKey: .verifier)
        createdAt = try record.decode(Date.self, forKey: .createdAt)
        expectedUser = try record.decodeIfPresent(String.self, forKey: .expectedUser)
        authority = try IdentityAuthority.read(from: decoder)
        link = try record.decodeIfPresent(IdentityLinkIntent.self, forKey: .link)
        if let link { try link.validate(); guard authority == .fallsoftVipiProduction else { throw URLError(.userAuthenticationRequired) } }
    }
    func encode(to encoder: any Encoder) throws {
        var record = encoder.container(keyedBy: Keys.self)
        try record.encode(state, forKey: .state)
        try record.encode(verifier, forKey: .verifier)
        try record.encode(createdAt, forKey: .createdAt)
        try record.encodeIfPresent(expectedUser, forKey: .expectedUser)
        try record.encodeIfPresent(link, forKey: .link)
        try authority.write(to: encoder)
    }
}

struct IdentityLinkIntent: Codable {
    let accountID: UUID; let requestID: UUID; let oldUserID: String; let deviceID: UUID; let deviceSecret: String
    var expectedSharedUser: String?
    func validate() throws {
        guard oldUserID.hasPrefix("user_"), oldUserID.count <= 128,
              deviceSecret.range(of: "^[A-Za-z0-9_-]{43}$", options: .regularExpression) != nil,
              expectedSharedUser == nil || (expectedSharedUser!.hasPrefix("user_") && expectedSharedUser!.count <= 128) else { throw URLError(.userAuthenticationRequired) }
    }
}
struct IdentityLinkProfile: Codable {
    let id: UUID; let username: String; let display_name: String
}
struct IdentityLinkJournal: Codable {
    let linkFormatVersion: Int
    let intent: IdentityLinkIntent; let candidate: VipiSession; let verifiedProfile: IdentityLinkProfile?
    private enum CodingKeys: String, CodingKey { case linkFormatVersion, intent, candidate, verifiedProfile }
    init(intent: IdentityLinkIntent, candidate: VipiSession, verifiedProfile: IdentityLinkProfile? = nil) throws {
        self.linkFormatVersion = 1; self.intent = intent; self.candidate = candidate; self.verifiedProfile = verifiedProfile
        try validate()
    }
    init(from decoder: any Decoder) throws {
        let record = try decoder.container(keyedBy: CodingKeys.self)
        linkFormatVersion = try record.decode(Int.self, forKey: .linkFormatVersion)
        intent = try record.decode(IdentityLinkIntent.self, forKey: .intent)
        candidate = try record.decode(VipiSession.self, forKey: .candidate)
        verifiedProfile = try record.decodeIfPresent(IdentityLinkProfile.self, forKey: .verifiedProfile)
        try validate()
    }
    private func validate() throws {
        try intent.validate()
        guard linkFormatVersion == 1, candidate.authority == .fallsoftVipiProduction,
              candidate.userID.hasPrefix("user_"), candidate.userID.count <= 128,
              (1...32768).contains(candidate.accessToken.count), (1...16384).contains(candidate.refreshToken.count),
              intent.expectedSharedUser == nil || intent.expectedSharedUser == candidate.userID,
              verifiedProfile == nil || verifiedProfile?.id == intent.accountID else { throw URLError(.userAuthenticationRequired) }
    }
}
struct IdentityLinkReceipt: Decodable {
    let request_id: UUID; let account_id: UUID; let authority_id: String; let authentication_subject: String; let binding_revision: Int
    func validate(intent: IdentityLinkIntent, candidate: VipiSession) throws {
        guard request_id == intent.requestID, account_id == intent.accountID, authority_id == IdentityAuthority.fallsoftVipiProduction.rawValue,
              authentication_subject == candidate.userID, binding_revision == 1 else { throw URLError(.userAuthenticationRequired) }
    }
}

/// Email opens hosted AuthKit, which also offers the environment's enabled providers.
enum SignInProvider: String, CaseIterable {
    case email = "authkit", google = "GoogleOAuth", apple = "AppleOAuth"
}

func signInAuthorizationURL(_ start: URL, provider: SignInProvider, reauthenticate: Bool) throws -> URL {
    guard var parts = URLComponents(url: start, resolvingAgainstBaseURL: false) else { throw URLError(.badURL) }
    var items = (parts.queryItems ?? []).filter { !["provider", "max_age", "screen_hint"].contains($0.name) }
    // Let AuthKit select the existing account's factors for fresh authentication.
    // A direct upstream OAuth session is not proof of recent authentication.
    items.append(URLQueryItem(name: "provider", value: reauthenticate ? "authkit" : provider.rawValue))
    if reauthenticate {
        items += [URLQueryItem(name: "max_age", value: "0"), URLQueryItem(name: "screen_hint", value: "sign-in")]
    }
    parts.queryItems = items
    guard let url = parts.url else { throw URLError(.badURL) }
    return url
}

private final class NoIdentityLinkRedirects: NSObject, URLSessionTaskDelegate, Sendable {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping @Sendable (URLRequest?) -> Void) { completionHandler(nil) }
}

@MainActor @Observable final class AuthenticationManager: NSObject, ASWebAuthenticationPresentationContextProviding {
    enum SessionFailure: Error { case signInRequired, accountChanged }
    private(set) var session: VipiSession?
    private(set) var busy = false
    var errorMessage: String?
    private var webSession: ASWebAuthenticationSession?
    private var refreshTask: Task<String, Error>?
    private var refreshID = UUID()
    private var sessionGeneration = UUID()
    private let callback = "co.fallsoft.vipi://auth/callback"
    private let identityHTTP = URLSession(configuration: .ephemeral, delegate: NoIdentityLinkRedirects(), delegateQueue: nil)
    #if DEBUG
    var qualificationLinkRequest: ((String, String, Data?, String, IdentityLinkIntent) async throws -> Data)?
    #endif
    private func storedSession() throws -> VipiSession? {
        guard let data = try KeychainStore.read(account: "session") else { return nil }
        return try JSONDecoder().decode(VipiSession.self, from: data)
    }
    override init() {
        super.init()
        if let data = try? KeychainStore.read(account: "session") { session = try? JSONDecoder().decode(VipiSession.self, from: data) }
    }
    func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.flatMap(\.windows).first(where: \.isKeyWindow) ?? ASPresentationAnchor()
    }
    func signIn(expectedUser: String? = nil, provider: SignInProvider = .email) {
        guard !busy else { return }
        errorMessage = nil
        do {
            let saved = try storedSession()
            if let saved {
                guard saved.userID == session?.userID else { throw SessionFailure.accountChanged }
            }
            let configuredID = Bundle.main.object(forInfoDictionaryKey: "WorkOSClientID") as? String ?? ""
            let authority = try IdentityAuthority.forSignIn(saved: saved?.authority, hasExpectedUser: expectedUser != nil, configuredClientID: configuredID)
            let boundUser = expectedUser ?? session?.userID
            try launchSignIn(authority: authority, expectedUser: boundUser, provider: provider)
        } catch { busy = false; errorMessage = String(localized: "We couldn’t start a secure sign-in. Please try again.") }
    }

    private func launchSignIn(authority: IdentityAuthority, expectedUser: String?, provider: SignInProvider, link: IdentityLinkIntent? = nil) throws {
            let client = PublicClient(clientID: authority.clientID)
            let authorization = try client.getAuthorizationUrlWithPKCE(redirectUri: callback, provider: "authkit")
            let pending = PendingSignIn(state: authorization.state, verifier: authorization.codeVerifier, createdAt: Date(), expectedUser: expectedUser, authority: authority, link: link)
            try KeychainStore.save(JSONEncoder().encode(pending), account: "pending-sign-in")
            let url = try signInAuthorizationURL(authorization.url, provider: provider, reauthenticate: expectedUser != nil || link != nil)
            busy = true
            let auth = ASWebAuthenticationSession(url: url, callbackURLScheme: "co.fallsoft.vipi") { [weak self] callbackURL, error in
                Task { @MainActor in
                    guard let self else { return }
                    if let callbackURL { await self.complete(callbackURL) }
                    else {
                        self.busy = false
                        KeychainStore.delete(account: "pending-sign-in")
                        if (error as? ASWebAuthenticationSessionError)?.code != .canceledLogin { self.errorMessage = String(localized: "We couldn’t finish signing in. Please try again.") }
                    }
                    self.webSession = nil
                }
            }
            auth.presentationContextProvider = self
            webSession = auth
            if !auth.start() {
                busy = false; webSession = nil; KeychainStore.delete(account: "pending-sign-in")
                errorMessage = String(localized: "Sign-in couldn’t open. Please try again.")
            }
    }
    /// Explicit migration; ordinary sign-in never links or replaces accounts.
    func beginFallsoftLink(accountID: UUID, device: DeviceCredential) {
        guard !busy else { return }; errorMessage = nil
        do {
            guard let current = try storedSession(), current.authority == .vipiProduction, current.userID == session?.userID else { throw SessionFailure.accountChanged }
            let previous = try KeychainStore.read(account: "pending-identity-link").map { try JSONDecoder().decode(IdentityLinkJournal.self, from: $0) }
            var intent = previous?.intent ?? IdentityLinkIntent(accountID: accountID, requestID: UUID(), oldUserID: current.userID,
                deviceID: device.id, deviceSecret: device.secret)
            if let previous { intent.expectedSharedUser = previous.candidate.userID }
            try intent.validate()
            guard intent.accountID == accountID, intent.oldUserID == current.userID, intent.deviceID == device.id, intent.deviceSecret == device.secret else { throw SessionFailure.accountChanged }
            try launchSignIn(authority: .fallsoftVipiProduction, expectedUser: nil, provider: .email, link: intent)
        } catch { errorMessage = String(localized: "We couldn’t start a secure sign-in. Please try again.") }
    }
    func complete(_ url: URL) async {
        guard url.scheme == "co.fallsoft.vipi", url.host == "auth", url.path == "/callback",
              url.port == nil, url.user == nil, url.password == nil, url.fragment == nil else { return }
        defer { busy = false; KeychainStore.delete(account: "pending-sign-in") }
        do {
            guard let data = try KeychainStore.read(account: "pending-sign-in"),
                  let pending = try? JSONDecoder().decode(PendingSignIn.self, from: data) else {
                errorMessage = String(localized: "We couldn’t verify this sign-in. Please start again."); return
            }
            let age = Date().timeIntervalSince(pending.createdAt)
            if age >= 600 {
                errorMessage = String(localized: "This sign-in attempt expired. Please start again."); return
            }
            guard age >= 0,
                  let parts = URLComponents(url: url, resolvingAgainstBaseURL: false),
                  let items = parts.queryItems,
                  items.filter({ $0.name == "state" }).count == 1,
                  items.first(where: { $0.name == "state" })?.value == pending.state,
                  items.filter({ $0.name == "code" }).count == 1,
                  let code = items.first(where: { $0.name == "code" })?.value, !code.isEmpty else {
                errorMessage = String(localized: "We couldn’t verify this sign-in. Please start again."); return
            }
            KeychainStore.delete(account: "pending-sign-in")
            let generation = sessionGeneration
            let client = PublicClient(clientID: pending.authority.clientID)
            let result = try await client.authenticateWithCode(code: code, codeVerifier: pending.verifier)
            guard generation == sessionGeneration else { throw SessionFailure.accountChanged }
            if let intent = pending.link {
                guard session?.isBound(to: .vipiProduction, subject: intent.oldUserID) == true else { throw SessionFailure.accountChanged }
                let candidate = VipiSession(userID: result.user.id, accessToken: result.accessToken, refreshToken: result.refreshToken, authority: pending.authority)
                let journal = try IdentityLinkJournal(intent: intent, candidate: candidate)
                try KeychainStore.save(JSONEncoder().encode(journal), account: "pending-identity-link")
                try await finishFallsoftLink(journal, generation: generation)
                return
            }
            if let expected = pending.expectedUser, result.user.id != expected {
                errorMessage = String(localized: "Sign in to the same account to continue."); return
            }
            if let session, !session.isBound(to: pending.authority, subject: result.user.id) {
                errorMessage = String(localized: "Sign in to the same account to continue."); return
            }
            let value = VipiSession(userID: result.user.id, accessToken: result.accessToken, refreshToken: result.refreshToken, authority: pending.authority)
            try KeychainStore.save(JSONEncoder().encode(value), account: "session")
            sessionGeneration = UUID()
            session = value
        } catch { errorMessage = String(localized: "We couldn’t finish signing in. Please try again.") }
    }
    func resumeFallsoftLink() async {
        guard !busy else { return }; busy = true; errorMessage = nil
        defer { busy = false }
        do {
            guard let data = try KeychainStore.read(account: "pending-identity-link") else { throw SessionFailure.accountChanged }
            try await finishFallsoftLink(JSONDecoder().decode(IdentityLinkJournal.self, from: data), generation: sessionGeneration)
        } catch { errorMessage = String(localized: "We couldn’t finish signing in. Please try again.") }
    }
    private func finishFallsoftLink(_ journal: IdentityLinkJournal, generation: UUID) async throws {
        guard let current = try storedSession() else { throw SessionFailure.accountChanged }
        let next = journal.candidate
        if journal.verifiedProfile != nil, current.isBound(to: .fallsoftVipiProduction, subject: next.userID) {
            guard let cache = try KeychainStore.read(account: "profile-" + next.userID),
                  try JSONDecoder().decode(IdentityLinkProfile.self, from: cache).id == journal.intent.accountID,
                  generation == sessionGeneration else { throw SessionFailure.accountChanged }
            if session?.isBound(to: .fallsoftVipiProduction, subject: next.userID) != true {
                sessionGeneration = UUID(); refreshID = UUID(); refreshTask?.cancel(); refreshTask = nil
            }
            session = current
            try KeychainStore.deleteChecked(account: "pending-identity-link")
            return
        }
        guard current.isBound(to: .vipiProduction, subject: journal.intent.oldUserID),
              session?.isBound(to: .vipiProduction, subject: journal.intent.oldUserID) == true else { throw SessionFailure.accountChanged }
        var oldToken = try await accessToken(for: journal.intent.oldUserID)
        let body = try JSONSerialization.data(withJSONObject: ["request_id": journal.intent.requestID.uuidString.lowercased(),
            "expected_account_id": journal.intent.accountID.uuidString.lowercased(), "fallsoft_access_token": next.accessToken])
        let receiptData: Data
        do { receiptData = try await linkRequest("POST", "/v1/identity-links/fallsoft", body: body, token: oldToken, intent: journal.intent) }
        catch let failure as ServiceFailure where failure.status == 401 && failure.code == "sign_in_required" {
            oldToken = try await accessToken(for: journal.intent.oldUserID, rejected: oldToken)
            receiptData = try await linkRequest("POST", "/v1/identity-links/fallsoft", body: body, token: oldToken, intent: journal.intent)
        }
        try JSONDecoder().decode(IdentityLinkReceipt.self, from: receiptData).validate(intent: journal.intent, candidate: next)
        let profileData = try await linkRequest("GET", "/v1/me", body: nil, token: next.accessToken, intent: journal.intent)
        let profile = try JSONDecoder().decode(IdentityLinkProfile.self, from: profileData)
        guard profile.id == journal.intent.accountID, generation == sessionGeneration,
              session?.isBound(to: .vipiProduction, subject: journal.intent.oldUserID) == true else { throw SessionFailure.accountChanged }
        let verified = try IdentityLinkJournal(intent: journal.intent, candidate: next, verifiedProfile: profile)
        try KeychainStore.save(JSONEncoder().encode(verified), account: "pending-identity-link")
        try KeychainStore.save(JSONEncoder().encode(profile), account: "profile-" + next.userID)
        try KeychainStore.save(JSONEncoder().encode(next), account: "session")
        guard let saved = try storedSession(), saved.isBound(to: .fallsoftVipiProduction, subject: next.userID),
              saved.accessToken == next.accessToken, saved.refreshToken == next.refreshToken else { throw SessionFailure.accountChanged }
        sessionGeneration = UUID(); refreshID = UUID(); refreshTask?.cancel(); refreshTask = nil; session = saved
        try KeychainStore.deleteChecked(account: "pending-identity-link")
    }
    private func linkRequest(_ method: String, _ path: String, body: Data?, token: String, intent: IdentityLinkIntent) async throws -> Data {
        #if DEBUG
        if let qualificationLinkRequest { return try await qualificationLinkRequest(method, path, body, token, intent) }
        #endif
        guard ["/v1/identity-links/fallsoft", "/v1/me"].contains(path), let url = URL(string: "https://api.mambovipi.app" + path) else { throw SessionFailure.accountChanged }
        var request = URLRequest(url: url); request.httpMethod = method; request.httpBody = body; request.timeoutInterval = 25
        request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
        request.setValue(intent.deviceID.uuidString.lowercased(), forHTTPHeaderField: "X-Vipi-Device-ID")
        request.setValue(intent.deviceSecret, forHTTPHeaderField: "X-Vipi-Device-Secret")
        if body != nil { request.setValue("application/json", forHTTPHeaderField: "Content-Type") }
        let (stream, response) = try await identityHTTP.bytes(for: request)
        guard let response = response as? HTTPURLResponse, response.expectedContentLength <= 65_536 else { throw URLError(.badServerResponse) }
        var result = Data()
        for try await byte in stream { guard result.count < 65_536 else { throw URLError(.dataLengthExceedsMaximum) }; result.append(byte) }
        guard (200...299).contains(response.statusCode) else {
            let error = (try? JSONSerialization.jsonObject(with: result) as? [String: Any])?["error"] as? String ?? "service_unavailable"
            throw ServiceFailure(status: response.statusCode, code: error)
        }
        return result
    }
    /// Refresh only after the service rejects this exact access token. Concurrent
    /// requests share one exchange; an old response cannot restore a signed-out
    /// session or attach a newly signed-in account to the old account's vault.
    func accessToken(for userID: String, rejected: String? = nil) async throws -> String {
        guard let current = session, current.userID == userID else { throw SessionFailure.signInRequired }
        let client = PublicClient(clientID: current.authority.clientID)
        guard let rejected, rejected == current.accessToken else { return current.accessToken }
        if let refreshTask { return try await refreshTask.value }
        let generation = sessionGeneration, id = UUID()
        refreshID = id
        let task = Task { @MainActor [self] () throws -> String in
            let result = try await Self.withRefreshRecovery {
                try await client.authenticateWithRefreshToken(refreshToken: current.refreshToken)
            }
            try Task.checkCancellation()
            guard sessionGeneration == generation, session?.refreshToken == current.refreshToken,
                result.user.id == userID else { throw SessionFailure.accountChanged }
            let value = VipiSession(userID: userID, accessToken: result.accessToken, refreshToken: result.refreshToken, authority: current.authority)
            try KeychainStore.save(JSONEncoder().encode(value), account: "session")
            session = value
            return value.accessToken
        }
        refreshTask = task
        defer { if refreshID == id { refreshTask = nil } }
        return try await task.value
    }
    static func refreshRequiresSignIn(_ error: Error) -> Bool {
        guard let error = error as? WorkOSError else { return false }
        switch error {
        case .authentication: return true
        case .badRequest(let payload):
            if payload.code == "invalid_grant" { return true }
            // WorkOS keeps OAuth's `error` field in raw, separate from `code`.
            if case .object(let body) = payload.raw { return body["error"] == .string("invalid_grant") }
            return false
        default: return false
        }
    }
    private static func withRefreshRecovery<T>(_ operation: () async throws -> T) async throws -> T {
        do { return try await operation() }
        catch {
            if refreshRequiresSignIn(error) { throw SessionFailure.signInRequired }
            throw error
        }
    }
    func signOutLocally() {
        sessionGeneration = UUID(); refreshID = UUID(); refreshTask?.cancel(); refreshTask = nil
        webSession?.cancel(); webSession = nil; session = nil; busy = false
        KeychainStore.delete(account: "session"); KeychainStore.delete(account: "pending-sign-in")
        KeychainStore.delete(account: "pending-identity-link")
    }
    func eraseLocalSession(for userID: String) throws {
        guard session?.userID == userID else { return }
        try KeychainStore.deleteChecked(account: "session")
        try KeychainStore.deleteChecked(account: "pending-sign-in")
        signOutLocally()
    }
}
