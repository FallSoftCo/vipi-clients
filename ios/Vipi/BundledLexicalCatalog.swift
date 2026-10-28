import CryptoKit
import Foundation
import SQLite3
import VipiCore
import zlib

/// Public app-signed data, expanded for the selected pair without storing messages.
actor BundledLexicalCatalog {
    static let shared = BundledLexicalCatalog()
    private struct Index: Decodable {
        struct File: Decodable {
            let id, file, sha256: String
            let bytes, compressed_bytes: Int
        }
        let schema, dictionary_release: String
        let files: [File]
    }
    private let resources: URL?
    private let root: URL?
    private var index: Index?
    private var verified: [String: (Int, Date)] = [:]
    init(resources: URL? = Bundle.main.resourceURL?.appendingPathComponent("lexical"),
         root: URL? = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first?.appendingPathComponent("lexical-public")) {
        self.resources = resources; self.root = root
    }
    private func loadIndex() throws -> Index? {
        if let index { return index }
        guard let path = resources?.appendingPathComponent("catalog.json"),
              FileManager.default.fileExists(atPath: path.path) else { return nil }
        let value = try JSONDecoder().decode(Index.self, from: Data(contentsOf: path))
        guard value.schema == "vipi-bundled-lexical-1",
              value.dictionary_release.range(of: "^[a-f0-9]{64}$", options: .regularExpression) != nil else {
            throw VocabularyPackError.invalid
        }
        index = value; return value
    }
    private func selected(_ pair: TranslationPair) throws -> [Index.File]? {
        guard pair.valid else { throw VocabularyPackError.invalid }
        guard let index = try loadIndex() else { return nil }
        let ids = ["d-" + pair.source, "d-" + pair.target,
                   "w-" + [pair.source, pair.target].sorted().joined(separator: "-")]
        return try ids.map { id in
            let matches = index.files.filter { $0.id == id }
            guard matches.count == 1, let row = matches.first,
                  row.file == id + ".sqlite.zlib", (512...536_870_912).contains(row.bytes),
                  (1...536_870_912).contains(row.compressed_bytes),
                  row.sha256.range(of: "^[a-f0-9]{64}$", options: .regularExpression) != nil else {
                throw VocabularyPackError.invalid
            }
            return row
        }
    }
    private func digest(_ file: URL) throws -> String {
        let input = try FileHandle(forReadingFrom: file)
        defer { try? input.close() }
        var hash = SHA256()
        while let data = try input.read(upToCount: 65_536), !data.isEmpty {
            try Task.checkCancellation(); hash.update(data: data)
        }
        return hash.finalize().map { String(format: "%02x", $0) }.joined()
    }
    private func stamp(_ file: URL) throws -> (Int, Date) {
        let values = try file.resourceValues(forKeys: [.fileSizeKey, .contentModificationDateKey])
        return (values.fileSize ?? -1, values.contentModificationDate ?? .distantPast)
    }
    private func databaseFile(_ row: Index.File) throws -> URL {
        guard let root, let resources else { throw VocabularyPackError.storage }
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        let name = row.id + "-" + row.sha256 + ".sqlite"
        let file = root.appendingPathComponent(name)
        if FileManager.default.fileExists(atPath: file.path) {
            let observed = try stamp(file)
            if observed.0 == row.bytes {
                if let prior = verified[name], prior.0 == observed.0, prior.1 == observed.1 { return file }
                if try digest(file) == row.sha256 { verified[name] = observed; return file }
            }
        }
        let temporary = root.appendingPathComponent("prepare-" + UUID().uuidString + ".sqlite")
        defer { try? FileManager.default.removeItem(at: temporary) }
        let input = try FileHandle(forReadingFrom: resources.appendingPathComponent(row.file))
        defer { try? input.close() }
        guard FileManager.default.createFile(atPath: temporary.path, contents: nil) else { throw VocabularyPackError.storage }
        let output = try FileHandle(forWritingTo: temporary)
        defer { try? output.close() }
        var stream = z_stream()
        guard inflateInit_(&stream, ZLIB_VERSION, Int32(MemoryLayout<z_stream>.size)) == Z_OK else {
            throw VocabularyPackError.invalid
        }
        defer { inflateEnd(&stream) }
        var hash = SHA256(), total = 0, compressed = 0
        var ended = false
        var buffer = [UInt8](repeating: 0, count: 65_536)
        while let data = try input.read(upToCount: 65_536), !data.isEmpty {
            try Task.checkCancellation()
            guard !ended else { throw VocabularyPackError.invalid }
            compressed += data.count
            guard compressed <= row.compressed_bytes else { throw VocabularyPackError.invalid }
            try data.withUnsafeBytes { raw in
                stream.next_in = UnsafeMutablePointer(mutating: raw.bindMemory(to: UInt8.self).baseAddress)
                stream.avail_in = uInt(data.count)
                repeat {
                    let capacity = buffer.count
                    let status = buffer.withUnsafeMutableBufferPointer { bytes -> Int32 in
                        stream.next_out = bytes.baseAddress
                        stream.avail_out = uInt(capacity)
                        return inflate(&stream, Z_NO_FLUSH)
                    }
                    let count = capacity - Int(stream.avail_out)
                    if status == Z_BUF_ERROR, stream.avail_in == 0, count == 0 { break }
                    guard status == Z_OK || status == Z_STREAM_END else { throw VocabularyPackError.invalid }
                    total += count
                    guard total <= row.bytes else { throw VocabularyPackError.invalid }
                    if count > 0 {
                        let chunk = Data(buffer.prefix(count))
                        hash.update(data: chunk); try output.write(contentsOf: chunk)
                    }
                    if status == Z_STREAM_END {
                        guard stream.avail_in == 0 else { throw VocabularyPackError.invalid }
                        ended = true; break
                    }
                } while stream.avail_in > 0 || stream.avail_out == 0
            }
        }
        guard ended, compressed == row.compressed_bytes, total == row.bytes,
              hash.finalize().map({ String(format: "%02x", $0) }).joined() == row.sha256 else {
            throw VocabularyPackError.invalid
        }
        try output.synchronize()
        try output.close()
        let header = try FileHandle(forReadingFrom: temporary)
        defer { try? header.close() }
        guard try header.read(upToCount: 16) == Data("SQLite format 3\0".utf8) else { throw VocabularyPackError.invalid }
        // POSIX rename atomically replaces a corrupt copy; existing readers keep their descriptor.
        guard rename(temporary.path, file.path) == 0 else { throw VocabularyPackError.storage }
        verified[name] = try stamp(file)
        for prior in try FileManager.default.contentsOfDirectory(at: root, includingPropertiesForKeys: nil) {
            let pattern = "^" + NSRegularExpression.escapedPattern(for: row.id) + "-[a-f0-9]{64}\\.sqlite$"
            if prior.lastPathComponent != name, prior.lastPathComponent.range(of: pattern, options: .regularExpression) != nil {
                try? FileManager.default.removeItem(at: prior); verified.removeValue(forKey: prior.lastPathComponent)
            }
        }
        return file
    }
    func prepare(_ pair: TranslationPair) throws -> Bool {
        guard let selected = try selected(pair) else { return false }
        for file in selected { _ = try databaseFile(file) }
        return true
    }
    private func withDatabase<T>(_ file: URL, _ body: (OpaquePointer) throws -> T) throws -> T {
        var pointer: OpaquePointer?
        guard sqlite3_open_v2(file.path, &pointer, SQLITE_OPEN_READONLY | SQLITE_OPEN_NOMUTEX, nil) == SQLITE_OK,
              let db = pointer else {
            if let pointer { sqlite3_close(pointer) }
            throw VocabularyPackError.storage
        }
        defer { sqlite3_close(db) }
        return try body(db)
    }
    func entries(original: String, translation: String, pair: TranslationPair) throws -> [VocabularyEntry] {
        guard TranslationIntegrity.preservesIdentifiers(original: original, translation: translation),
              let selected = try selected(pair) else { return [] }
        let files = try selected.map(databaseFile)
        return try withDatabase(files[0]) { left in
            try withDatabase(files[1]) { right in
                try withDatabase(files[2]) { witness in
                    try LexicalConcordance.entries(leftDB: left, rightDB: right, original: original,
                        translation: translation, source: pair.source, target: pair.target, witnessDB: witness)
                }
            }
        }
    }
}
