import Foundation
@main struct PinnedCacheProbe {
 static func main() {
  func key(_ i:Int)->Data { Data(String(i).utf8) }
  var cache=PinnedSnapshotCache<Int>(capacity:4096)
  cache.pin(key(0));cache.pin(key(1))
  for i in 0..<4096 { precondition(cache.insert(i,for:key(i))) }
  precondition(cache.insert(4096,for:key(4096)))
  precondition(cache.value(for:key(0))==0 && cache.value(for:key(1))==1 && cache.value(for:key(2))==nil && cache.value(for:key(4096))==4096)
  cache.unpin(key(0));cache.unpin(key(1))
  var full=PinnedSnapshotCache<Int>(capacity:1)
  full.pin(key(1));precondition(full.insert(1,for:key(1)))
  precondition(!full.insert(2,for:key(2)))
  full.unpin(key(1));precondition(full.insert(2,for:key(2)))
  precondition(full.value(for:key(1))==nil && full.value(for:key(2))==2)
  print("PASS: cap crossing evicts inactive; visible/inflight pins retained; saturation recovers after unpin")
 }
}
