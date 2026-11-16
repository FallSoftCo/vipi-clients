import Foundation
import NaturalLanguage
import Dispatch

@main struct NLTaggerAssetRequest {
 static func main() throws {
  let output=URL(fileURLWithPath:CommandLine.arguments[1])
  let languages=["en","es","fr","de","it","pt","ar","zh","ja","ko","sw"]
  let schemes:[NLTagScheme]=[.lexicalClass,.lemma]
  var rows:[[String:Any]]=[]
  func freeBytes() throws -> UInt64 {
   let values=try FileManager.default.attributesOfFileSystem(forPath:NSHomeDirectory())
   return (values[.systemFreeSize] as! NSNumber).uint64Value
  }
  func save(_ state:String) throws {
   let data:[String:Any]=["state":state,"scope":"macOS system-managed NLTagger assets; no chat content", "floor_bytes":3*1024*1024*1024, "requests":rows]
   try JSONSerialization.data(withJSONObject:data,options:[.prettyPrinted,.sortedKeys]).write(to:output,options:.atomic)
  }
  try save("running")
  for code in languages {
   let language=NLLanguage(rawValue:code)
   for scheme in schemes {
    let before=NLTagger.availableTagSchemes(for:.word,language:language)
    var row:[String:Any]=["language":code,"scheme":scheme.rawValue,"free_before":try freeBytes()]
    if before.contains(scheme) { row["status"]="already_available";rows.append(row);try save("running");continue }
    guard try freeBytes() >= 3*1024*1024*1024 else { row["status"]="disk_floor";rows.append(row);try save("stopped_disk_floor");return }
    // A timeout stops all further requests; it does not assert a system-managed
    // download was cancelled. The same request is never automatically repeated.
    let lock=NSLock(), signal=DispatchSemaphore(value:0)
    var callbackResult:String?, callbackError:String?
    NLTagger.requestAssets(for:language,tagScheme:scheme) { result,error in
     lock.lock(); callbackResult=String(describing:result);callbackError=error.map{String(describing:$0)};lock.unlock();signal.signal()
    }
    if signal.wait(timeout:.now()+180) == .timedOut {
     row["status"]="callback_timeout_unknown";rows.append(row);try save("stopped_unknown_request");return
    }
    lock.lock();let result=callbackResult, error=callbackError;lock.unlock()
    row["status"]="callback";row["result"]=result ?? "unknown";if let error { row["error"]=error }
    row["free_after"]=try freeBytes()
    row["available_after"]=NLTagger.availableTagSchemes(for:.word,language:language).contains(scheme)
    rows.append(row);try save("running")
   }
  }
  try save("completed")
 }
}
