import Foundation
@main struct Probe {
 static func main()throws {
  let args=CommandLine.arguments;let output=try FrozenCandidateQualification.run(root:URL(fileURLWithPath:args[1]),en:URL(fileURLWithPath:args[2]))
  let data=try JSONSerialization.data(withJSONObject:output,options:[.sortedKeys]);guard data.count<=16<<20 else{throw FrozenContextPack.Failure.bound};try data.write(to:URL(fileURLWithPath:args[3]),options:.withoutOverwriting)
 }
}
