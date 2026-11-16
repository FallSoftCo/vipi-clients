import Foundation
import CryptoKit
import VipiCore
@main struct FrameVaultProbe {
 static func main() throws {
  let root=URL(fileURLWithPath:CommandLine.arguments[1]), account=UUID(), key=SymmetricKey(data:Data((0..<32).map(UInt8.init)))
  let first=ReviewedFrameIdentity(verifiedReviewedPattern:true,sourceLanguage:"en",targetLanguage:"fr",patternID:"reviewed:bank:financial",sourceFace:"bank",targetFace:"banque",meaning:"financial institution",reading:"")!
  let second=ReviewedFrameIdentity(verifiedReviewedPattern:true,sourceLanguage:"en",targetLanguage:"fr",patternID:"reviewed:bank:river",sourceFace:"bank",targetFace:"rive",meaning:"river shore",reading:"")!
  let changed=ReviewedFrameIdentity(verifiedReviewedPattern:true,sourceLanguage:"en",targetLanguage:"fr",patternID:"reviewed:bank:financial",sourceFace:"bank",targetFace:"banque",meaning:"different meaning",reading:"")!
  var vault=try MessageVault(account:account,directory:root,testKey:key)
  var store=VocabularyFamiliarityStore(vault:vault)
  let initial=try store.frameHistory([first,second],day:100)
  precondition(initial.allSatisfy {$0 != nil && !$0!.seen})
  precondition(store.observeFrames([first],day:100) && store.frameHistoryRevision==1)
  precondition(store.observeFrames([first],day:100) && store.frameHistoryRevision==1)
  precondition(store.observeFrames([first],day:99) && store.frameHistoryRevision==1)
  let state=try store.frameHistory([first,second,changed],day:101)
  precondition(state[0]!.seen && state[0]!.due && !state[1]!.seen && !state[2]!.seen)
  precondition(store.observeFrames([second],day:100))
  let idKey=try vault.transaction { try vault.get("immersion-metadata","id-key-v1")! }
  let mac=HMAC<SHA256>.authenticationCode(for:first.encoded,using:SymmetricKey(data:idKey)).map{String(format:"%02x",$0)}.joined()
  try vault.transaction { try vault.put("immersion-frame-exposure-next",mac,Data("bad".utf8)) }
  store=VocabularyFamiliarityStore(vault:vault)
  let corrupted=try store.frameHistory([first,second],day:101)
  precondition(corrupted[0]==nil && corrupted[1]!.seen)
  try vault.close()
  precondition(!store.observeFrames([second],day:102))
  vault=try MessageVault(account:account,directory:root,testKey:key)
  store=VocabularyFamiliarityStore(vault:vault)
  let reopened=try store.frameHistory([second],day:101)
  precondition(reopened[0]!.seen)
  let path=vault.url
  try vault.close()
  for suffix in ["","-wal","-shm"] {
   let p=URL(fileURLWithPath:path.path+suffix)
   if let bytes=try? Data(contentsOf:p) { precondition(bytes.range(of:Data("bank".utf8)) == nil && bytes.range(of:Data("banque".utf8)) == nil) }
  }
  print("PASS: real SQLite/AES vault, v2 exposure, same-day/clock reversal, sense separation, corruption isolation, close/reopen, no plaintext face; injected test key only")
 }
}
