import Foundation
import CryptoKit
import VipiCore
@main struct StarterVaultProbe {
 static func main() throws {
  let root=URL(fileURLWithPath:CommandLine.arguments[1]), account=UUID(), key=SymmetricKey(data:Data((0..<32).map(UInt8.init)))
  let frame=ReviewedFrameIdentity(verifiedReviewedPattern:true,sourceLanguage:"en",targetLanguage:"sw",patternID:"frame:music",sourceFace:"music",targetFace:"muziki",meaning:"music",reading:"")!
  let starter=ReviewedStarterIdentity(verifiedReviewedEntry:true,sourceLanguage:"en",targetLanguage:"sw",entryID:"word-en-sw-i",conceptID:"i",partOfSpeech:"pron",guardValue:"",canonicalSource:"i",targetFace:"mimi",reading:"")!
  let changed=ReviewedStarterIdentity(verifiedReviewedEntry:true,sourceLanguage:"en",targetLanguage:"sw",entryID:"word-en-sw-i",conceptID:"i",partOfSpeech:"pron",guardValue:"",canonicalSource:"i",targetFace:"different",reading:"")!
  precondition(ReviewedStarterIdentity(verifiedReviewedEntry:false,sourceLanguage:"en",targetLanguage:"sw",entryID:"word-en-sw-i",conceptID:"i",partOfSpeech:"pron",guardValue:"",canonicalSource:"i",targetFace:"mimi",reading:"")==nil)
  var vault=try MessageVault(account:account,directory:root,testKey:key)
  var store=VocabularyFamiliarityStore(vault:vault)
  let initial=try store.mixedHistory(frames:[frame],starters:[starter,changed],day:100)
  precondition(!initial.0[0]!.seen && !initial.1[0]!.seen && !initial.1[1]!.seen)
  precondition(store.observeFrames([frame],day:100) && store.observeStarters([starter],day:100))
  precondition(store.frameHistoryRevision==1 && store.starterHistoryRevision==1)
  precondition(store.observeStarters([starter],day:100) && store.starterHistoryRevision==1)
  precondition(store.observeStarters([starter],day:99) && store.starterHistoryRevision==1)
  let next=try store.mixedHistory(frames:[frame],starters:[starter,changed],day:101)
  precondition(next.0[0]!.seen && next.0[0]!.due && next.1[0]!.seen && next.1[0]!.due && !next.1[1]!.seen)
  let ids=try vault.transaction { (try vault.ids("immersion-frame-exposure-next"),try vault.ids("immersion-starter-exposure-next"),try vault.ids("immersion-exposure")) }
  precondition(ids.0.count==1 && ids.1.count==1 && ids.2.isEmpty && ids.0[0] != ids.1[0])
  try vault.transaction { try vault.put("immersion-starter-exposure-next",ids.1[0],Data("bad".utf8)) }
  store=VocabularyFamiliarityStore(vault:vault)
  let bad=try store.mixedHistory(frames:[frame],starters:[starter],day:101)
  precondition(bad.0[0]!.seen && bad.1[0]==nil)
  try vault.close();precondition(!store.observeStarters([starter],day:102))
  vault=try MessageVault(account:account,directory:root,testKey:key);store=VocabularyFamiliarityStore(vault:vault)
  let reopened=try store.mixedHistory(frames:[frame],starters:[starter],day:101)
  precondition(reopened.0[0]!.seen && reopened.1[0]==nil)
  let db=vault.url;try vault.close()
  for suffix in ["","-wal","-shm"] { if let data=try? Data(contentsOf:URL(fileURLWithPath:db.path+suffix)) { precondition(data.range(of:Data("muziki".utf8)) == nil && data.range(of:Data("mimi".utf8)) == nil) } }
  print("PASS: real encrypted vault mixed frame/starter snapshot, namespace separation, dwell-only explicit calls, same-day/clock reversal, changed face, corruption isolation and reopen; test key injected")
 }
}
