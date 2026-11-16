import Foundation
import CryptoKit
import VipiCore
func checkStarterIdentities(_ path:String) throws -> Int {
 let fixture=try JSONSerialization.jsonObject(with:Data(contentsOf:URL(fileURLWithPath:path))) as! [String:Any]
 func bytes(_ hex:String)->Data { var d=Data();var i=hex.startIndex;while i<hex.endIndex {let n=hex.index(i,offsetBy:2);d.append(UInt8(hex[i..<n],radix:16)!);i=n};return d }
 let key=SymmetricKey(data:bytes(fixture["test_key_hex"] as! String));var hashes:[String:String]=[:];var count=0
 for row in fixture["cases"] as! [[String:Any]] {
  let f=row["fields"] as! [String:String]
  let value=ReviewedStarterIdentity(verifiedReviewedEntry:row["verified_current_occurrence"] as! Bool,sourceLanguage:f["source_language"]!,targetLanguage:f["target_language"]!,entryID:f["entry_id"]!,conceptID:f["concept_id"]!,partOfSpeech:f["pos"]!,guardValue:f["guard"]!,canonicalSource:f["canonical_source"]!,targetFace:f["target_face"]!,reading:f["reading"]!)
  if let expected=row["expected_encoded_hex"] as? String {
   precondition(value != nil && value!.encoded==bytes(expected))
   let mac=HMAC<SHA256>.authenticationCode(for:value!.encoded,using:key).map{String(format:"%02x",$0)}.joined()
   precondition(mac == row["expected_hmac_sha256"] as! String);hashes[row["id"] as! String]=mac
  } else { precondition(value == nil) }
  count += 1
 }
 for relation in fixture["relations"] as! [[String:Any]] {
  let a=hashes[relation["a"] as! String],b=hashes[relation["b"] as! String]
  precondition((a != nil && b != nil && a == b)==(relation["equal"] as! Bool))
 }
 return count
}
