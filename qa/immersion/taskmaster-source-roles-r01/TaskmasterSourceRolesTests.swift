import Foundation
import CryptoKit
import XCTest
import VipiCore
@testable import Vipi
@MainActor final class TaskmasterSourceRolesTests:XCTestCase {
 func testFrozenSourceRoles()throws {
  let root=URL(fileURLWithPath:try XCTUnwrap(ProcessInfo.processInfo.environment["VIPI_TASKMASTER_ROLES_QA"]))
  let bytes=try Data(contentsOf:root.appendingPathComponent("inputs-200.json"))
  XCTAssertEqual(SHA256.hash(data:bytes).map{String(format:"%02x",$0)}.joined(),"8ced39c191466dcd6a4f86a3dd738444c8e8d58609f1dbd1d06e46b001c5dc6d")
  let input=try JSONSerialization.jsonObject(with:bytes) as! [String:Any]
  let cases=input["cases"] as! [[String:Any]]
  let en=FileManager.default.urls(for:.cachesDirectory,in:.userDomainMask)[0].appendingPathComponent("lexical-public/d-en-5b16dafff9b2a27474792104bad11195ba8aff2236c134cf0265257b92727d68.sqlite")
  let source=try FrozenNativeCandidateProvider(dictionaryURL:en,expectedSHA256:"5b16dafff9b2a27474792104bad11195ba8aff2236c134cf0265257b92727d68",expectedRelease:"6032509770e483e6dd4bf5625eeadf5c24c8b0a3d91555d2df72d4e1993cef7c",expectedInventory:"8c97e9de2ce8e94ce9754475a85eb27cd956ee0ba69491fe270376e3177ceb17")

  func range(_ r:NSRange)->[Int]{[r.location,NSMaxRange(r)]}
  var output:[[String:Any]]=[]
  for row in cases {
   let original=row["text"] as! String
   let supplied=(row["protected_ranges_utf16"] as! [[Int]]).map{NSRange(location:$0[0],length:$0[1]-$0[0])}
   let tick=DispatchTime.now().uptimeNanoseconds
   let s=try source.inspect(original:original,protectedRanges:supplied)
   let observations:[[String:Any]]=s.role.observations.map{o in
    ["utf16":range(o.range),"text":o.original,"role":o.role.rawValue,"raw_tag":o.rawLexicalTag as Any? ?? NSNull(),"unknown_reason":o.unknownReason as Any? ?? NSNull(),"overlaps_protection":o.overlapsProtection,"noun_eligible":o.nounEligible]
   }
   let record:[String:Any]=["id":row["id"]!,"original":original,"source_sha256":FrozenCandidateCatalog.hash(original),"status":s.role.status.rawValue,"available_schemes":s.role.availableSchemes,"words":s.input.words.map(range),"sentences":LocalImmersion.sentences(original,language:"en").map(range),"observations":observations,"supplied_protection":supplied.map(range),"role_detected_names":s.role.detectedNames.map(range),"role_protected_ranges":s.role.protectedRanges.map(range),"source_overlap_protections":s.input.protected.map(range),"source_masks":s.input.sourceMasks,"elapsed_ns":DispatchTime.now().uptimeNanoseconds-tick]
   XCTAssertTrue(s.role.matches(original:original,language:"en",wordRanges:s.input.words,protectedRanges:supplied))
   output.append(record)
  }
  XCTAssertEqual(output.count,200)
  let report:[String:Any]=["schema":"vipi.taskmaster-source-roles.1","cases":output,"translation_calls":0,"selection_calls":0,"source_inspections":200]
  let result=try JSONSerialization.data(withJSONObject:report,options:[.sortedKeys]);XCTAssertLessThanOrEqual(result.count,8<<20)
  let a=XCTAttachment(data:result,uniformTypeIdentifier:"public.json");a.name="taskmaster-source-roles-r01";a.lifetime = .keepAlways;add(a)
 }
}
