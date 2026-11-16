import Foundation

/// Packs an already verified, request-bound source-reference pool. It does not
/// admit meanings, infer POS, translate, read history or record exposure.
public enum AdditiveReferenceSelection {
    public enum History: Sendable { case novel, seen(due: Bool), unavailable }
    public static func select(units: [SourceReferenceUnit], history: [History],
                              nativeSourceTokenCount: Int, density: Double,
                              preserveProducerPriority: Bool = false) -> [SourceReferenceUnit]? {
        guard units.count == history.count, units.count <= 4096,
              (1...16_384).contains(nativeSourceTokenCount), density.isFinite, (0...0.75).contains(density) else { return nil }
        guard density > 0 else { return [] }
        let total = min(nativeSourceTokenCount,max(1,Int(Double(nativeSourceTokenCount)*0.75)))
        let novelBudget = max(1,Int(Double(nativeSourceTokenCount)*density))
        return select(units:units,history:history,novelBudget:novelBudget,totalCeiling:total,preserveProducerPriority:preserveProducerPriority)
    }
    public static func select(units: [SourceReferenceUnit], history: [History],
                              novelBudget: Int, totalCeiling total: Int,
                              preserveProducerPriority: Bool = false) -> [SourceReferenceUnit]? {
        guard units.count == history.count, units.count <= 4096,
              (0...16_384).contains(novelBudget), (0...16_384).contains(total) else { return nil }
        guard novelBudget > 0, total > 0 else { return [] }
        let indices=Array(units.indices)
        func order(_ a:Int,_ b:Int)->Bool {
            let x=units[a], y=units[b]
            if x.range.location != y.range.location { return x.range.location < y.range.location }
            if x.range.length != y.range.length { return x.range.length < y.range.length }
            return x.referenceID.utf8.lexicographicallyPrecedes(y.referenceID.utf8)
        }
        let newCandidates = indices.filter { if case .novel=history[$0] { return true };return false }
        // A reviewed producer may already order by frame/content/length/rank.
        // Preserve that validated precedence; sort only the final presentation.
        let new = preserveProducerPriority ? newCandidates : newCandidates.sorted(by:order)
        let seen = indices.filter { if case .seen=history[$0] { return true };return false }.sorted { a,b in
            let da:Bool = { if case .seen(let due)=history[a] { return due };return false }()
            let db:Bool = { if case .seen(let due)=history[b] { return due };return false }()
            return da == db ? order(a,b) : da
        }
        var chosen:[Int]=[], used=0, newUsed=0
        func add(_ i:Int) -> Bool {
            let unit=units[i], cost=unit.nativeSourceTokens
            guard (1...128).contains(cost), used + cost <= total, chosen.count < 128,
                  !chosen.contains(where: { NSIntersectionRange(units[$0].range,unit.range).length > 0 }) else { return false }
            if case .novel=history[i], newUsed + cost > novelBudget { return false }
            chosen.append(i);used += cost
            if case .novel=history[i] { newUsed += cost }
            return true
        }
        for i in new { if add(i) { break } }
        for i in seen { _ = add(i) }
        for i in new { _ = add(i) }
        return chosen.sorted(by:order).map { units[$0] }
    }
}
