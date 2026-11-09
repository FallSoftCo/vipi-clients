import Foundation
import SQLite3
import XCTest
@testable import Vipi

final class FrozenCandidateProducerTests:XCTestCase {
 func testFullCatalogProducerAndActualNativeObservations()throws {
  try XCTSkipUnless(ProcessInfo.processInfo.environment["VIPI_CANDIDATE_QA_DIRECTORY"] != nil,"Explicit private qualification only")
  let root=URL(fileURLWithPath:try XCTUnwrap(ProcessInfo.processInfo.environment["VIPI_CANDIDATE_QA_DIRECTORY"]))
  let en=FileManager.default.urls(for:.cachesDirectory,in:.userDomainMask)[0].appendingPathComponent("lexical-public/d-en-5b16dafff9b2a27474792104bad11195ba8aff2236c134cf0265257b92727d68.sqlite")
  var pointer:OpaquePointer?;XCTAssertEqual(sqlite3_open_v2(en.path,&pointer,SQLITE_OPEN_READONLY,nil),SQLITE_OK);let db=try XCTUnwrap(pointer);defer{sqlite3_close(db)}
  let provider=try FrozenNativeCandidateProvider(dictionaryURL:en,expectedSHA256:"5b16dafff9b2a27474792104bad11195ba8aff2236c134cf0265257b92727d68",expectedRelease:"6032509770e483e6dd4bf5625eeadf5c24c8b0a3d91555d2df72d4e1993cef7c",expectedInventory:"8c97e9de2ce8e94ce9754475a85eb27cd956ee0ba69491fe270376e3177ceb17")
  XCTAssertEqual(FrozenCandidateProducer.Observation.apple("Noun"),"noun");XCTAssertEqual(FrozenCandidateProducer.Observation.apple("Adjective"),"adj");XCTAssertEqual(FrozenCandidateProducer.Observation.apple("Adverb"),"adv");XCTAssertNil(FrozenCandidateProducer.Observation.apple(nil));XCTAssertNil(FrozenCandidateProducer.Observation.apple("Verb"));XCTAssertNil(FrozenCandidateProducer.Observation.apple("PersonalName"))
  // Synthetic interleaved focus groups: focus A owns2,4 and B owns3,5.
  // Frozen gate preserves global producer indices, not focus-group order.
  XCTAssertEqual(FrozenCandidateProducer.qualifiedOrder(ordinary:[0,1],admittedGroups:[[2,4],[3,5]]),[0,1,2,3,4,5])
  XCTAssertEqual(FrozenCandidateProducer.qualifiedOrder(ordinary:[0],admittedGroups:[[],[3,5],[2,4]]),[0,2,3,4,5])
  XCTAssertThrowsError(try provider.inspect(original:"𐐀 a",protectedRanges:[NSRange(location:0,length:1)]))
  let protectedWater=try provider.inspect(original:"water",protectedRanges:[NSRange(location:0,length:5)])
  XCTAssertTrue(protectedWater.input.protected.contains(NSRange(location:0,length:5)))
  let result=try FrozenCandidateQualification.run(root:root,en:en){text,supplied in
   let snapshot=try provider.inspect(original:text,protectedRanges:supplied),role=snapshot.role,recognition=snapshot.recognition
   XCTAssertTrue(snapshot.input.protected.starts(with:supplied))
   return(snapshot.input,["role_status":role.status.rawValue,"schemes":role.availableSchemes,"named_ranges":role.detectedNames.map(FrozenCandidateProducer.pair),"dictionary_release":recognition.dictionaryRelease,"dictionary_inventory":recognition.dictionaryInventory,"units":recognition.units.count,"nil_form_focus":recognition.units.flatMap(\.forms).filter{$0.intrinsicRange==nil}.count])
  }
  let reference=try JSONSerialization.jsonObject(with:Data(contentsOf:root.appendingPathComponent("reference.json"))) as! [String:Any]
  for (expected,got) in zip(reference["cases"] as! [[String:Any]],result["cases"] as! [[String:Any]]) {
   let diagnostic=got["diagnostic"] as! [String:Any]
   for key in ["candidates","geometry_rejections","experimental_geometry_rejections"] {XCTAssertTrue((diagnostic[key] as! NSArray).isEqual(to:expected[key] as! [Any]),"frozen parity \(expected["case_id"]!) \(key)")}
   XCTAssertEqual(diagnostic["baseline_candidate_count"] as? Int,expected["baseline_candidate_count"] as? Int)
   let decisions=diagnostic["selections"] as! [String:[String:Any]],original=expected["original_decisions"] as! [String:[String:Any]],qualified=expected["original_qualified_decisions"] as! [String:[String:Any]]
   for state in ["all_function","all_function_global300"] {for arm in ["baseline","experimental"] {XCTAssertTrue((decisions[state]![arm] as! NSDictionary).isEqual(to:original[state]![arm] as! [AnyHashable:Any]))};XCTAssertTrue((decisions[state]!["qualified"] as! NSDictionary).isEqual(to:qualified[state]!))}
  }
  let data=try JSONSerialization.data(withJSONObject:result,options:[.sortedKeys]);XCTAssertLessThanOrEqual(data.count,16<<20)
  let attachment=XCTAttachment(data:data,uniformTypeIdentifier:"public.json");attachment.name="native-candidate-producer-r01";attachment.lifetime = .keepAlways;add(attachment)
  XCTAssertEqual((result["cases"] as? [[String:Any]])?.count,52)
 }
}
