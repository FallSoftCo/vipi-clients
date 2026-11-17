import Foundation
@main struct Probe {
 @MainActor static func main() async throws {
  let rows:[(String,String,String?)] = [
   ("masked_context","I love music. https://example.com/path","en"),("short_like","I like music.","en"),("short_love","I love music.","en"),("short_heard","I heard music.","en"),
   ("es","Me gusta escuchar música con mis amigos.","es"),("fr","J’aime écouter de la musique avec mes amis.","fr"),
   ("de","Ich höre gerne Musik mit meinen Freunden.","de"),("it","Mi piace ascoltare musica con i miei amici.","it"),
   ("pt","Gosto de ouvir música com os meus amigos.","pt"),("ja","友達と一緒に音楽を聴くのが好きです。","ja"),
   ("ko","친구들과 함께 음악을 듣는 것을 좋아해요.","ko"),("zh","我喜欢和朋友一起听音乐。","zh"),
   ("ar","أحب الاستماع إلى الموسيقى مع أصدقائي.","ar"),("sw","Ninapenda kusikiliza muziki pamoja na marafiki zangu.","sw"),
   ("conflict_fr_en","Je suis très content with my friend and I love music.","en"),("conflict_de_en","Ich liebe Musik and I like to listen with my friends.","en"),("pain","pain",nil),("gift","gift",nil),("room","room",nil),("code","code",nil),("name","Alice",nil),
   ("url","https://example.com/music",nil),("code_only","`hello_world`",nil),
   ("masked_one","pain https://example.com/music",nil),("polish","To jest bardzo piękna muzyka i przyjaciele.",nil),
   ("mixed","I love 音楽.",nil),("oversize",String(repeating:"a",count:16385),nil)]
  let detector=MessageLanguage();var out:[[String:Any]]=[];var failures:[String]=[]
  for (id,text,expected) in rows {let value=try await detector.identify(text,automatic:true);let ok=value==expected;if !ok{failures.append(id)};out.append(["id":id,"actual":value as Any? ?? NSNull(),"expected":expected as Any? ?? NSNull(),"pass":ok])}
  let task=Task { try await detector.identify("I love music.",automatic:true) }; task.cancel(); do { _ = try await task.value; failures.append("cancellation") } catch is CancellationError {}
  let legacy=try await detector.identify("I like music.");if legacy != nil {failures.append("legacy_full")}
  let seams:[(String,String?,Double?,String?)] = [("threshold_low","en",0.699,nil),("threshold_equal","en",0.70,"en"),("zh_normalize","zh-Hant",0.99,"zh"),("unsupported","pl",0.99,nil),("no_confidence","en",nil,nil)]
  for (id,code,c,expect) in seams{let value=MessageLanguage.nativeFallback(code:code,confidence:c);let ok=value==expect;if !ok{failures.append(id)};out.append(["id":id,"actual":value as Any? ?? NSNull(),"expected":expect as Any? ?? NSNull(),"pass":ok])}
  let payload:[String:Any]=["scope":"macOS actual MessageLanguage source, real NaturalLanguage + CLD2 adapter and masking; synthetic samples, no production app","legacy_full_short":legacy as Any? ?? NSNull(),"rows":out,"failures":failures]
  let d=try JSONSerialization.data(withJSONObject:payload,options:[.prettyPrinted,.sortedKeys]);try d.write(to:URL(fileURLWithPath:CommandLine.arguments[1]),options:.withoutOverwriting);print("cases=\(out.count) failures=\(failures)");if !failures.isEmpty {exit(1)}
 }
}
