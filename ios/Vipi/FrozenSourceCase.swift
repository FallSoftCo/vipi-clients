import Foundation
import CryptoKit

struct FrozenSourceCase {
    private struct Tables: Decodable { let unicode_version: String; let lower, upper, title: [[UInt32]] }
    private let tables: Tables
    init() throws {
        guard let data=Data(base64Encoded:FrozenSourceCaseTables.base64),
              SHA256.hash(data:data).map({String(format:"%02x",$0)}).joined()==FrozenSourceCaseTables.sha256 else { throw FrozenContextPack.Failure.identity }
        tables=try JSONDecoder().decode(Tables.self,from:data)
        guard tables.unicode_version=="15.0.0" else { throw FrozenContextPack.Failure.identity }
    }
    private func contains(_ scalar:UInt32,_ ranges:[[UInt32]])->Bool {
        var low=0,high=ranges.count
        while low<high { let mid=low+(high-low)/2;if ranges[mid][1]<scalar {low=mid+1}else{high=mid} }
        return low<ranges.count && ranges[low][0]<=scalar
    }
    /// Source must first pass the pinned tokenizer's assigned-scalar bound.
    func isLower(_ text:String)->Bool {
        var lower=false
        for s in text.unicodeScalars {
            if contains(s.value,tables.lower) {lower=true}
            else if contains(s.value,tables.upper) || contains(s.value,tables.title) {return false}
        }
        return lower
    }
    func firstIsUpper(_ text:String)->Bool { text.unicodeScalars.first.map {contains($0.value,tables.upper)} ?? false }
}
