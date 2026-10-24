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
}

struct VipiSession: Codable, Sendable {
    let userID: String
    let accessToken: String
    let refreshToken: String
}
private struct PendingSignIn: Codable { let state: String; let verifier: String; let createdAt: Date }

@MainActor @Observable final class AuthenticationManager: NSObject, ASWebAuthenticationPresentationContextProviding {
    private(set) var session: VipiSession?
    private(set) var busy = false
    var errorMessage: String?
    private var webSession: ASWebAuthenticationSession?
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
    func signIn() {
        guard !busy else { return }
        guard let client else { errorMessage = "Sign-in isn’t available yet. Please try again shortly."; return }
        errorMessage = nil
        do {
            let authorization = try client.getAuthorizationUrlWithPKCE(redirectUri: callback, provider: "authkit")
            let pending = PendingSignIn(state: authorization.state, verifier: authorization.codeVerifier, createdAt: Date())
            try KeychainStore.save(JSONEncoder().encode(pending), account: "pending-sign-in")
            busy = true
            let auth = ASWebAuthenticationSession(url: authorization.url, callbackURLScheme: "co.fallsoft.vipi") { [weak self] callbackURL, error in
                Task { @MainActor in
                    guard let self else { return }
                    if let callbackURL { await self.complete(callbackURL) }
                    else {
                        self.busy = false
                        KeychainStore.delete(account: "pending-sign-in")
                        if (error as? ASWebAuthenticationSessionError)?.code != .canceledLogin { self.errorMessage = "We couldn’t finish signing in. Please try again." }
                    }
                    self.webSession = nil
                }
            }
            auth.presentationContextProvider = self
            webSession = auth
            if !auth.start() {
                busy = false; webSession = nil; KeychainStore.delete(account: "pending-sign-in")
                errorMessage = "Sign-in couldn’t open. Please try again."
            }
        } catch { busy = false; errorMessage = "We couldn’t start a secure sign-in. Please try again." }
    }
    func complete(_ url: URL) async {
        guard url.scheme == "co.fallsoft.vipi", url.host == "auth", url.path == "/callback",
              url.port == nil, url.user == nil, url.password == nil, url.fragment == nil,
              let client else { return }
        defer { busy = false; KeychainStore.delete(account: "pending-sign-in") }
        do {
            guard let data = try KeychainStore.read(account: "pending-sign-in"),
                  let pending = try? JSONDecoder().decode(PendingSignIn.self, from: data), (0..<600).contains(Date().timeIntervalSince(pending.createdAt)),
                  let parts = URLComponents(url: url, resolvingAgainstBaseURL: false),
                  let items = parts.queryItems,
                  items.filter({ $0.name == "state" }).count == 1,
                  items.first(where: { $0.name == "state" })?.value == pending.state,
                  items.filter({ $0.name == "code" }).count == 1,
                  let code = items.first(where: { $0.name == "code" })?.value, !code.isEmpty else {
                errorMessage = "We couldn’t verify this sign-in. Please start again."; return
            }
            KeychainStore.delete(account: "pending-sign-in")
            let result = try await client.authenticateWithCode(code: code, codeVerifier: pending.verifier)
            let value = VipiSession(userID: result.user.id, accessToken: result.accessToken, refreshToken: result.refreshToken)
            try KeychainStore.save(JSONEncoder().encode(value), account: "session")
            session = value
        } catch { errorMessage = "We couldn’t finish signing in. Please try again." }
    }
    func signOutLocally() {
        webSession?.cancel(); webSession = nil; session = nil; busy = false
        KeychainStore.delete(account: "session"); KeychainStore.delete(account: "pending-sign-in")
    }
}
