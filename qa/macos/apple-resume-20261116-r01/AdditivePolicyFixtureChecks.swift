import Foundation
import VipiCore
func checkAdditiveFixtures(_ path:String) throws -> Int {
 let input=try JSONSerialization.jsonObject(with:Data(contentsOf:URL(fileURLWithPath:path))) as! [String:Any]
 var passed=0
 for fixture in input["cases"] as! [[String:Any]] {
  let rows=fixture["candidates"] as! [[String:Any]]
  let eligible=rows.filter { $0["eligible"] as! Bool }.sorted {
   let a=$0["priority"] as? Int ?? ($0["start"] as! Int), b=$1["priority"] as? Int ?? ($1["start"] as! Int)
   return a == b ? ($0["start"] as! Int) < ($1["start"] as! Int) : a < b
  }
  let units=eligible.map { row -> SourceReferenceUnit in
   let start=row["start"] as! Int, end=row["end"] as! Int, id=row["id"] as! String
   return .init(range:NSRange(location:start,length:end-start),original:id,translated:id,reading:nil,referenceID:id,catalogSHA256:String(repeating:"a",count:64),nativeSourceTokens:row["cost"] as? Int ?? 1)
  }
  let history:[AdditiveReferenceSelection.History]=eligible.map { row in
   (row["state"] as! String)=="seen" ? .seen(due:row["due"] as! Bool) : .novel
  }
  let result=AdditiveReferenceSelection.select(units:units,history:history,novelBudget:fixture["novel_budget"] as! Int,totalCeiling:fixture["hard_ceiling"] as! Int,preserveProducerPriority:true)!
  precondition(result.map(\.referenceID)==(fixture["expected"] as! [String]),"fixture \(fixture["id"]!)")
  passed += 1
 }
 return passed
}
