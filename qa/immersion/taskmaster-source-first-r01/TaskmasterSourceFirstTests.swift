import Foundation
import CryptoKit
import XCTest
import VipiCore
@testable import Vipi
@MainActor final class TaskmasterSourceFirstTests:XCTestCase {
 func testFrozenSourceFirst()throws {
  let root=URL(fileURLWithPath:try XCTUnwrap(ProcessInfo.processInfo.environment["VIPI_TASKMASTER_SOURCE_FIRST_QA"]))
  let bytes=try Data(contentsOf:root.appendingPathComponent("inputs-200.json"))
  XCTAssertEqual(SHA256.hash(data:bytes).map{String(format:"%02x",$0)}.joined(),"8ced39c191466dcd6a4f86a3dd738444c8e8d58609f1dbd1d06e46b001c5dc6d")
  let rows=(try JSONSerialization.jsonObject(with:bytes) as! [String:Any])["cases"] as! [[String:Any]]
  let initialization=DispatchTime.now().uptimeNanoseconds
  let prior=root.deletingLastPathComponent().appendingPathComponent("native-candidate-producer-r01")
  let config=try JSONSerialization.jsonObject(with:Data(contentsOf:prior.appendingPathComponent("bindings.json"))) as! [String:Any]
  let packRoot=URL(fileURLWithPath:config["pack_input_directory"] as! String)
  let en=FileManager.default.urls(for:.cachesDirectory,in:.userDomainMask)[0].appendingPathComponent("lexical-public/d-en-5b16dafff9b2a27474792104bad11195ba8aff2236c134cf0265257b92727d68.sqlite")
  let pack=try FrozenContextPack(url:packRoot.appendingPathComponent("context.sqlite"),expectedSHA256:"cd7a8667ff0df53610ef19aa585398e24470716dd23af6d640b7c77dbc3badb4",expectedMetadata:config["expected_metadata"] as! [String:String],dictionaryURLs:["en":en,"es":packRoot.appendingPathComponent("d-es.sqlite")])
  let catalog=try FrozenCandidateCatalog(url:prior.appendingPathComponent("catalog.sqlite"),manifestURL:prior.appendingPathComponent("manifest.json"),manifestSHA256:"9c0d7af245a599bfaadc07dc6fb84c41a3bf72b5e657adcee0b7b68efa96a281",contextPack:pack)
  let provider=try FrozenNativeCandidateProvider(dictionaryURL:en,expectedSHA256:"5b16dafff9b2a27474792104bad11195ba8aff2236c134cf0265257b92727d68",expectedRelease:"6032509770e483e6dd4bf5625eeadf5c24c8b0a3d91555d2df72d4e1993cef7c",expectedInventory:"8c97e9de2ce8e94ce9754475a85eb27cd956ee0ba69491fe270376e3177ceb17")
  let initializationNS=DispatchTime.now().uptimeNanoseconds-initialization
  func range(_ r:NSRange)->[Int]{[r.location,NSMaxRange(r)]}
  var result:[[String:Any]]=[]
  for row in rows {
   let text=row["text"] as! String,supplied=(row["protected_ranges_utf16"] as! [[Int]]).map{NSRange(location:$0[0],length:$0[1]-$0[0])}
   let tick=DispatchTime.now().uptimeNanoseconds
   let prepared=try provider.prepare(original:text,protectedRanges:supplied,catalog:catalog,pack:pack)
   let prepareNS=DispatchTime.now().uptimeNanoseconds-tick
   let selectionTick=DispatchTime.now().uptimeNanoseconds
   let selection=try provider.select(prepared,catalog:catalog,knownFamilyIDs:[],withholdFunction:false,density:0.25)
   let selectionNS=DispatchTime.now().uptimeNanoseconds-selectionTick
   let assessments=prepared.currentEvidence.mapValues{a -> [String:Any] in
    ["chosen_rule_id":a.chosenRuleID as Any? ?? NSNull(),"rejections":a.rejectionReasons,"heads":a.heads.map{h -> [String:Any] in ["id":h.headID,"eligible":h.conditionallyEligible,"rejections":h.rejectionReasons,"supported_tuples":h.supportedTuples.map{["source_form":$0.sourceFormID,"target_form":$0.targetFormID,"source_term":$0.sourceTermID,"target_term":$0.targetTermID]}]}]
   }
   let snapshot=prepared.snapshot,out=prepared.output
   let observations:[[String:Any]]=snapshot.role.observations.map{o in ["utf16":range(o.range),"text":o.original,"raw_tag":o.rawLexicalTag as Any? ?? NSNull(),"unknown_reason":o.unknownReason as Any? ?? NSNull(),"overlaps_protection":o.overlapsProtection,"noun_eligible":o.nounEligible]}
   let record:[String:Any]=["id":row["id"]!,"original":text,"source_sha256":FrozenCandidateCatalog.hash(text),"candidates":out.candidates,"ordinary_count":out.ordinaryCount,"geometry_rejections":out.geometryRejections,"conditional_geometry_rejections":out.conditionalGeometryRejections,"gates":out.gates,"qualified_indices_before_current_evidence":out.qualifiedIndices,"qualified_indices":prepared.qualifiedIndices,"assessments":assessments,"selection":selection,"words":snapshot.input.words.map(range),"sentences":LocalImmersion.sentences(text,language:"en").map(range),"supplied_protection":supplied.map(range),"source_protections":snapshot.input.protected.map(range),"source_masks":snapshot.input.sourceMasks,"role_status":snapshot.role.status.rawValue,"roles":observations,"input_identity":out.inputIdentity,"bundle_identity":out.bundleIdentity,"prepare_ns":prepareNS,"select_ns":selectionNS]
   XCTAssertTrue(snapshot.role.matches(original:text,language:"en",wordRanges:snapshot.input.words,protectedRanges:supplied))
   result.append(record)
  }
  XCTAssertEqual(result.count,200)
  let report:[String:Any]=["schema":"vipi.taskmaster-source-first.1","cases":result,"catalog_sha256":catalog.sha256,"context_sha256":pack.contentSHA256,"identity_preparation_ns":initializationNS,"known_family_ids":[String](),"withhold_function":false,"density":0.25,"translation_calls":0]
  let tick=DispatchTime.now().uptimeNanoseconds
  let output=try JSONSerialization.data(withJSONObject:report,options:[.sortedKeys]);XCTAssertLessThanOrEqual(output.count,16<<20)
  let a=XCTAttachment(data:output,uniformTypeIdentifier:"public.json");a.name="taskmaster-source-first-r01";a.lifetime = .keepAlways;add(a)
  let timing=try JSONSerialization.data(withJSONObject:["serialization_ns":DispatchTime.now().uptimeNanoseconds-tick,"output_bytes":output.count],options:[.sortedKeys]);let t=XCTAttachment(data:timing,uniformTypeIdentifier:"public.json");t.name="taskmaster-source-first-timing";t.lifetime = .keepAlways;add(t)
 }
}
