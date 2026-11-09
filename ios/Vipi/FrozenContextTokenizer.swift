import Foundation
import CryptoKit

/// Exact Python Unicode-15 scalar classification/casefold; no native-word approximation.
/// Foundation NFC must pass the frozen normalization probes before qualification.
struct FrozenContextTokenizer {
    enum Failure: Error { case invalidTables, unsupportedScalar, inputBound }
    struct Token: Equatable {
        let original: String
        let normalized: String
        let range: NSRange
        let hasAlphabeticScalar: Bool
    }
    private struct Tables: Decodable {
        let unicode_version: String
        let assigned: [[UInt32]], alnum: [[UInt32]], alpha: [[UInt32]], space: [[UInt32]]
        let casefold: [[FoldPart]]
        enum FoldPart: Decodable {
            case scalar(UInt32), sequence([UInt32])
            init(from decoder: Decoder) throws {
                let c = try decoder.singleValueContainer()
                if let n = try? c.decode(UInt32.self) { self = .scalar(n) }
                else { self = .sequence(try c.decode([UInt32].self)) }
            }
        }
    }
    private let tables: Tables
    private let folds: [UInt32: [UInt32]]
    init() throws {
        guard let data = Data(base64Encoded: FrozenContextUnicodeTables.base64),
              SHA256.hash(data: data).map({ String(format: "%02x", $0) }).joined() == FrozenContextUnicodeTables.sha256 else { throw Failure.invalidTables }
        let decoded = try JSONDecoder().decode(Tables.self, from: data)
        guard decoded.unicode_version == "15.0.0" else { throw Failure.invalidTables }
        var map: [UInt32: [UInt32]] = [:]
        for pair in decoded.casefold {
            guard pair.count == 2, case let .scalar(key) = pair[0], case let .sequence(value) = pair[1], map[key] == nil else { throw Failure.invalidTables }
            map[key] = value
        }
        tables = decoded; folds = map
    }
    private func contains(_ scalar: UInt32, _ ranges: [[UInt32]]) -> Bool {
        var low = 0, high = ranges.count
        while low < high {
            let mid = low + (high-low)/2
            if ranges[mid][1] < scalar { low = mid+1 } else { high = mid }
        }
        return low < ranges.count && ranges[low][0] <= scalar
    }
    /// Classifier uses original scalar alpha, while rule windows use normalized token alpha.
    func originalHasAlphabeticScalar(_ text: String) -> Bool {
        text.unicodeScalars.contains { contains($0.value, tables.alpha) }
    }
    func normalize(_ text: String) throws -> String {
        guard text.utf16.count <= 16_384 else { throw Failure.inputBound }
        guard text.unicodeScalars.allSatisfy({ contains($0.value, tables.assigned) }) else { throw Failure.unsupportedScalar }
        let nfc = text.precomposedStringWithCanonicalMapping
        var values: [UInt32] = []
        for scalar in nfc.unicodeScalars {
            guard contains(scalar.value, tables.assigned) else { throw Failure.unsupportedScalar }
            values.append(contentsOf: folds[scalar.value] ?? [scalar.value])
        }
        var result = String.UnicodeScalarView(); var pendingSpace = false
        for value in values {
            if contains(value, tables.space) { if !result.isEmpty { pendingSpace = true }; continue }
            if pendingSpace { result.append(Unicode.Scalar(32)!); pendingSpace = false }
            guard let scalar = Unicode.Scalar(value) else { throw Failure.invalidTables }
            result.append(scalar)
        }
        return String(result)
    }
    func tokenize(_ source: String) throws -> [Token] {
        guard source.utf16.count <= 16_384 else { throw Failure.inputBound }
        let scalars = Array(source.unicodeScalars)
        guard scalars.allSatisfy({ contains($0.value, tables.assigned) }) else { throw Failure.unsupportedScalar }
        var offsets = [0]
        for scalar in scalars { offsets.append(offsets.last! + (scalar.value > 0xffff ? 2 : 1)) }
        let original = source as NSString
        var output: [Token] = []; var i = 0
        while i < scalars.count {
            let start = i, value = scalars[i].value
            if contains(value, tables.alnum) {
                i += 1
                while i < scalars.count && contains(scalars[i].value, tables.alnum) { i += 1 }
                while i+1 < scalars.count && (scalars[i].value == 39 || scalars[i].value == 0x2019) && contains(scalars[i+1].value, tables.alnum) {
                    i += 2
                    while i < scalars.count && contains(scalars[i].value, tables.alnum) { i += 1 }
                }
            } else if value == 95 || contains(value, tables.space) { i += 1; continue }
            else { i += 1 }
            let range = NSRange(location: offsets[start], length: offsets[i]-offsets[start])
            let piece = original.substring(with: range), normalized = try normalize(piece)
            output.append(.init(original: piece, normalized: normalized, range: range,
                                hasAlphabeticScalar: normalized.unicodeScalars.contains { contains($0.value, tables.alpha) }))
        }
        return output
    }
}
