import Foundation
import Security

struct DeviceCredential: Codable, Sendable {
    let id: UUID
    let secret: String
    static func load(vault: MessageVault) throws -> Self {
        try vault.transaction {
            if let data = try vault.get("local", "service-device") {
                return try JSONDecoder().decode(Self.self, from: data)
            }
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
        guard SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes) == errSecSuccess else {
            throw MessageVault.Failure.invalidRecord
        }
        let secret = Data(bytes).base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(
            of: "/", with: "_"
        ).replacingOccurrences(of: "=", with: "")
        return Self(id: UUID(), secret: secret)
    }

}

struct ServiceFailure: Error {
    let status: Int
    let code: String
}
