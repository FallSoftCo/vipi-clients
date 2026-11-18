import Foundation

enum HistoryBackupStore {
    struct ImportResult: Sendable { let added: Int; let existing: Int }

    private static func accountDirectory(_ account: UUID, baseDirectory: URL?) throws -> URL {
        let base = baseDirectory ?? FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        guard base.isFileURL else { throw CocoaError(.fileWriteInvalidFileName) }
        let support = base.standardizedFileURL.resolvingSymlinksInPath()
        let root = support.appendingPathComponent("HistoryFiles", isDirectory: true)
        let attributed = root.appendingPathComponent("accounts-v1", isDirectory: true)
        guard root.resolvingSymlinksInPath() == root, attributed.resolvingSymlinksInPath() == attributed else { throw CocoaError(.fileWriteInvalidFileName) }
        // Legacy exports used UUID run folders directly below HistoryFiles.
        // A separate namespace prevents guessing that such a folder is an account.
        return attributed.appendingPathComponent(account.uuidString.lowercased(), isDirectory: true)
    }
    static func directory(account: UUID, baseDirectory: URL? = nil) throws -> URL {
        var owned = try accountDirectory(account, baseDirectory: baseDirectory)
        guard owned.resolvingSymlinksInPath() == owned else { throw CocoaError(.fileWriteInvalidFileName) }
        try FileManager.default.createDirectory(at: owned, withIntermediateDirectories: true,
            attributes: [.posixPermissions: 0o700, .protectionKey: FileProtectionType.completeUntilFirstUserAuthentication])
        var values = URLResourceValues(); values.isExcludedFromBackup = true; try owned.setResourceValues(values)
        return owned
    }
    static func temporaryURL(account: UUID, baseDirectory: URL? = nil) throws -> URL {
        try directory(account: account, baseDirectory: baseDirectory).appendingPathComponent(UUID().uuidString.lowercased() + ".vipihistory")
    }
    static func exportURL(account: UUID, baseDirectory: URL? = nil) throws -> URL {
        let folder = try directory(account: account, baseDirectory: baseDirectory).appendingPathComponent(UUID().uuidString.lowercased(), isDirectory: true)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: false,
            attributes: [.posixPermissions: 0o700, .protectionKey: FileProtectionType.completeUntilFirstUserAuthentication])
        let date = ISO8601DateFormatter().string(from: Date()).prefix(10)
        return folder.appendingPathComponent("Vipi chat backup \(date).vipihistory")
    }
    static func removeStaged(_ url: URL, account: UUID, baseDirectory: URL? = nil) {
        guard url.isFileURL, let owned = try? accountDirectory(account, baseDirectory: baseDirectory),
              url.standardizedFileURL.deletingLastPathComponent() == owned,
              url.pathExtension == "vipihistory", UUID(uuidString: url.deletingPathExtension().lastPathComponent) != nil,
              url.resolvingSymlinksInPath() == url.standardizedFileURL else { return }
        try? FileManager.default.removeItem(at: url)
    }
    static func removeExport(_ url: URL, account: UUID, baseDirectory: URL? = nil) {
        let parent = url.standardizedFileURL.deletingLastPathComponent()
        guard url.isFileURL, let owned = try? accountDirectory(account, baseDirectory: baseDirectory),
              parent.deletingLastPathComponent() == owned, UUID(uuidString: parent.lastPathComponent) != nil,
              url.pathExtension == "vipihistory", url.resolvingSymlinksInPath() == url.standardizedFileURL else { return }
        try? FileManager.default.removeItem(at: url)
        if (try? FileManager.default.contentsOfDirectory(atPath: parent.path).isEmpty) == true {
            try? FileManager.default.removeItem(at: parent)
        }
    }
    /// Only the confirmed account's attributed staging belongs to this deletion.
    /// Unscoped legacy files have no proven owner and remain untouched.
    static func erasePrivateFiles(account: UUID, baseDirectory: URL? = nil) throws {
        let owned = try accountDirectory(account, baseDirectory: baseDirectory)
        if FileManager.default.fileExists(atPath: owned.path) ||
            (try? owned.resourceValues(forKeys: [.isSymbolicLinkKey]).isSymbolicLink) == true {
            // FileManager removes a symbolic link itself, never its target.
            try FileManager.default.removeItem(at: owned)
        }
    }

    enum StageCheckpoint: Sendable, Equatable { case created, copiedChunk, synchronized }
    /// Copy only encrypted bytes from an arbitrary document provider. The
    /// bounded private copy is what both verification passes subsequently read.
    static func stage(_ selected: URL, to destination: URL,
                      checkpoint: @Sendable (StageCheckpoint) throws -> Void = { _ in }) throws -> URL {
        try Task.checkCancellation()
        let authorized = selected.startAccessingSecurityScopedResource()
        defer { if authorized { selected.stopAccessingSecurityScopedResource() } }
        guard destination.isFileURL, destination.resolvingSymlinksInPath() == destination.standardizedFileURL else { throw CocoaError(.fileWriteInvalidFileName) }
        guard !FileManager.default.fileExists(atPath: destination.path) else { throw CocoaError(.fileWriteFileExists) }
        guard FileManager.default.createFile(atPath: destination.path, contents: nil,
            attributes: [.posixPermissions: 0o600, .protectionKey: FileProtectionType.completeUntilFirstUserAuthentication]) else { throw CocoaError(.fileWriteUnknown) }
        do {
            try checkpoint(.created); try Task.checkCancellation()
            let input = try FileHandle(forReadingFrom: selected), output = try FileHandle(forWritingTo: destination)
            defer { try? input.close(); try? output.close() }
            var count = 0
            while true {
                try Task.checkCancellation()
                let bytes = try input.read(upToCount: 65_536) ?? Data()
                if bytes.isEmpty { break }
                count += bytes.count
                guard count <= HistoryBackupCodec.maxFileBytes else { throw HistoryBackupCodec.Failure.damaged }
                try output.write(contentsOf: bytes)
                try checkpoint(.copiedChunk); try Task.checkCancellation()
            }
            try Task.checkCancellation()
            guard count >= 56 else { throw HistoryBackupCodec.Failure.damaged }
            try output.synchronize()
            try checkpoint(.synchronized); try Task.checkCancellation()
            try FileManager.default.setAttributes([.posixPermissions: 0o400], ofItemAtPath: destination.path)
            return destination
        } catch {
            if destination.resolvingSymlinksInPath() == destination.standardizedFileURL { try? FileManager.default.removeItem(at: destination) }
            throw error
        }
    }

    static func export(vault: MessageVault, password: String, to url: URL) throws {
        let history = try ConversationHistory(vault: vault)
        let peers = try history.backupPeerIDs()
        // Writer rejects an existing destination before this operation owns any
        // output. A rejected caller URL must never be removed by failure cleanup.
        let expectedPath = url.resolvingSymlinksInPath()
        let writer = try HistoryBackupCodec.Writer(url: url, password: password, account: vault.account)
        do {
            try writer.append(.metadata(account: vault.account, createdAt: Int64(Date().timeIntervalSince1970 * 1000)))
            for peerID in peers {
                try Task.checkCancellation()
                let peer: HistoryBackupPeer = try vault.transaction {
                    let id = peerID.uuidString.lowercased()
                    if let data = try vault.get("contact", id) {
                        let value = try JSONDecoder().decode(ChatProfile.self, from: data)
                        return HistoryBackupPeer(id: peerID, username: value.username, displayName: value.display_name)
                    }
                    if let data = try vault.get("imported-peer", id) { return try JSONDecoder().decode(HistoryBackupPeer.self, from: data) }
                    return HistoryBackupPeer(id: peerID, username: nil, displayName: nil)
                }
                try writer.append(.peer(peer))
            }
            var messages = 0
            for peerID in peers {
                var cursor: String?
                repeat {
                    try Task.checkCancellation()
                    let page = try autoreleasepool { try history.backupPage(peer: peerID, before: cursor) }
                    for message in page.messages { try writer.append(.message(message)); messages += 1 }
                    cursor = page.next
                } while cursor != nil
            }
            try writer.append(.end(records: 1 + peers.count + messages, peers: peers.count, messages: messages))
            try writer.finish()
            try Task.checkCancellation()
        } catch {
            if url.resolvingSymlinksInPath() == expectedPath { try? FileManager.default.removeItem(at: url) }
            throw error
        }
    }

    static func merge(vault: MessageVault, staged: URL, password: String,
                      verified: HistoryBackupCodec.Summary) throws -> ImportResult {
        try vault.transaction {
            var added = 0, existing = 0
            let reread = try HistoryBackupCodec.inspect(url: staged, password: password, account: vault.account) { record in
                try Task.checkCancellation()
                switch record {
                case .peer(let peer):
                    let id = peer.id.uuidString.lowercased()
                    if try vault.get("contact", id) == nil, try vault.get("imported-peer", id) == nil {
                        try vault.put("imported-peer", id, JSONEncoder().encode(peer))
                    }
                case .message(let message):
                    if try contains(vault: vault, message: message) { existing += 1 }
                    else {
                        try vault.put("imported", message.id.uuidString.lowercased(), JSONEncoder().encode(message))
                        try ConversationHistory.record(vault, kind: "imported", id: message.id, peer: message.peer, createdAt: message.createdAt)
                        added += 1
                    }
                default: break
                }
            }
            guard reread == verified else { throw HistoryBackupCodec.Failure.damaged }
            return ImportResult(added: added, existing: existing)
        }
    }

    /// An ID collision must never overwrite a live record or change its state.
    private static func contains(vault: MessageVault, message: HistoryBackupMessage) throws -> Bool {
        let id = message.id.uuidString.lowercased(); var found = false
        for kind in ["draft", "incoming", "outgoing", "imported"] {
            guard let bytes = try vault.get(kind, id) else { continue }
            let value: HistoryBackupMessage
            if kind == "imported" { value = try JSONDecoder().decode(HistoryBackupMessage.self, from: bytes) }
            else if kind == "draft" {
                let row = try JSONDecoder().decode(DraftChat.self, from: bytes)
                value = HistoryBackupMessage(id: row.id, peer: row.recipient, outgoing: true, createdAt: row.createdAt, text: row.text)
            } else {
                let row = try JSONDecoder().decode(StoredChat.self, from: bytes), outgoing = kind == "outgoing"
                value = HistoryBackupMessage(id: row.envelope.id, peer: outgoing ? row.envelope.recipient : row.envelope.sender,
                    outgoing: outgoing, createdAt: row.envelope.createdAt, text: row.text)
            }
            guard value == message else { throw HistoryBackupCodec.Failure.conflict }
            found = true
        }
        return found
    }
}
