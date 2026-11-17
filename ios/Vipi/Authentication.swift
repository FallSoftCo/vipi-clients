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

struct VipiSession: Codable, Sendable {
    let userID: String
    let accessToken: String
    let refreshToken: String
}
private struct PendingSignIn: Codable { let state: String; let verifier: String; let createdAt: Date; var expectedUser: String? }

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
    private var client: PublicClient? {
        guard let id = Bundle.main.object(forInfoDictionaryKey: "WorkOSClientID") as? String, id.hasPrefix("client_") else { return nil }
        return PublicClient(clientID: id)
    }
    override init() {
        super.init()
        if let data = try? KeychainStore.read(account: "session") { session = try? JSONDecoder().decode(VipiSession.self, from: data) }
    }
    func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.flatMap(\.windows).first(where: \.isKeyWindow) ?? ASPresentationAnchor()
    }
    func signIn(expectedUser: String? = nil) {
        guard !busy else { return }
        guard let client else { errorMessage = String(localized: "Sign-in isn’t available yet. Please try again shortly."); return }
        errorMessage = nil
        do {
            let authorization = try client.getAuthorizationUrlWithPKCE(redirectUri: callback, provider: "authkit")
            let pending = PendingSignIn(state: authorization.state, verifier: authorization.codeVerifier, createdAt: Date(), expectedUser: expectedUser)
            try KeychainStore.save(JSONEncoder().encode(pending), account: "pending-sign-in")
            var url = URLComponents(url: authorization.url, resolvingAgainstBaseURL: false)!
            if expectedUser != nil {
                url.queryItems = (url.queryItems ?? []).filter { !["max_age", "screen_hint"].contains($0.name) } + [URLQueryItem(name: "max_age", value: "0"), URLQueryItem(name: "screen_hint", value: "sign-in")]
            }
            busy = true
            let auth = ASWebAuthenticationSession(url: url.url!, callbackURLScheme: "co.fallsoft.vipi") { [weak self] callbackURL, error in
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
        } catch { busy = false; errorMessage = String(localized: "We couldn’t start a secure sign-in. Please try again.") }
    }
    func complete(_ url: URL) async {
        guard url.scheme == "co.fallsoft.vipi", url.host == "auth", url.path == "/callback",
              url.port == nil, url.user == nil, url.password == nil, url.fragment == nil,
              let client else { return }
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
            let result = try await client.authenticateWithCode(code: code, codeVerifier: pending.verifier)
            guard generation == sessionGeneration else { throw SessionFailure.accountChanged }
            if let expected = pending.expectedUser, result.user.id != expected {
                errorMessage = String(localized: "Sign in to the same account to continue."); return
            }
            let value = VipiSession(userID: result.user.id, accessToken: result.accessToken, refreshToken: result.refreshToken)
            try KeychainStore.save(JSONEncoder().encode(value), account: "session")
            sessionGeneration = UUID()
            session = value
        } catch { errorMessage = String(localized: "We couldn’t finish signing in. Please try again.") }
    }
    /// Refresh only after the service rejects this exact access token. Concurrent
    /// requests share one exchange; an old response cannot restore a signed-out
    /// session or attach a newly signed-in account to the old account's vault.
    func accessToken(for userID: String, rejected: String? = nil) async throws -> String {
        guard let current = session, current.userID == userID, let client else { throw SessionFailure.signInRequired }
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
            let value = VipiSession(userID: userID, accessToken: result.accessToken, refreshToken: result.refreshToken)
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
    }
    func eraseLocalSession(for userID: String) throws {
        guard session?.userID == userID else { return }
        try KeychainStore.deleteChecked(account: "session")
        try KeychainStore.deleteChecked(account: "pending-sign-in")
        signOutLocally()
    }
}
