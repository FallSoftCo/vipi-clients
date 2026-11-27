import Foundation

/// An invitation pre-fills a search. Opening it never sends or trusts a message.
enum FriendInvitationLink {
    static func username(in url: URL) -> String? {
        guard url.absoluteString.count <= 160,
            let parts = URLComponents(url: url, resolvingAgainstBaseURL: false),
            parts.user == nil, parts.password == nil, parts.port == nil,
            parts.query == nil, parts.fragment == nil
        else { return nil }
        let prefix: String
        switch (parts.scheme?.lowercased(), parts.host?.lowercased()) {
        case ("https", "api.mambovipi.app"): prefix = "/invite/"
        case ("co.fallsoft.vipi", "invite"): prefix = "/"
        default: return nil
        }
        guard parts.percentEncodedPath.hasPrefix(prefix) else { return nil }
        let name = String(parts.percentEncodedPath.dropFirst(prefix.count)).lowercased()
        guard name.range(of: "^[a-z][a-z0-9_]{2,23}$", options: .regularExpression) != nil,
            !["vipi", "vbot", "bot", "admin", "administrator", "support", "security", "fallsoft", "mambovipi", "system"]
                .contains(name)
        else { return nil }
        return name
    }
}
