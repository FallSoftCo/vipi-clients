import Foundation
@MainActor func checkCarrierMetadata() throws -> Int {
    var count = 0
    func check(_ head: String, _ source: String, _ context: String, _ focus: [Int], _ carrier: [Int]?, _ rule: String?, valid: Bool) throws {
        var value: [String:Any] = ["context":context,"focus_utf16":focus]
        if let carrier { value["carrier_utf16"] = carrier }
        if let rule { value["carrier_rule"] = rule }
        let variant = try JSONDecoder().decode(SourceFrameLookup.Variant.self,from:JSONSerialization.data(withJSONObject:value))
        var accepted = false
        do { _ = try SourceFrameLookup.reviewedCarrier(variant,head:head,source:source); accepted = true } catch { }
        precondition(accepted == valid, "Unexpected attachment validation: \(value)")
        count += 1
    }
    let ar = "supplied-singular-definite-article-1", ko = "hangul-noun-particles-1"
    try check("ماء","ar","الماء",[2,5],[0,5],ar,valid:true)
    for suffix in ["은","이","을","과","도","만","에","에서","의"] {
        try check("책","ko","책"+suffix,[0,1],[0,1+suffix.utf16.count],ko,valid:true)
    }
    for suffix in ["는","가","를","와","도","만","에","에서","의"] {
        try check("커피","ko","커피"+suffix,[0,2],[0,2+suffix.utf16.count],ko,valid:true)
    }
    try check("책","ko","책를",[0,1],[0,2],ko,valid:false)
    try check("커피","ko","커피을",[0,2],[0,3],ko,valid:false)
    try check("책","ko","책에서도",[0,1],[0,4],ko,valid:false)
    try check("책","ko","책을",[0,1],nil,ko,valid:false)
    try check("책","ko","책을",[0,1],[0,2],nil,valid:false)
    try check("책","ko","책을",[0,1],[0,2],"unknown",valid:false)
    try check("책","ar","책을",[0,1],[0,2],ko,valid:false)
    try check("책","ko","책을",[1,2],[0,2],ko,valid:false)
    try check("ماء","ar","بالماء",[3,6],[0,6],ar,valid:false)
    try check("الماء","ar","الالماء",[2,7],[0,7],ar,valid:false)
    try check("مَاء","ar","المَاء",[2,6],[0,6],ar,valid:false)
    try check("책","ko","책을",[0,1],[0,3],ko,valid:false)
    return count
}
