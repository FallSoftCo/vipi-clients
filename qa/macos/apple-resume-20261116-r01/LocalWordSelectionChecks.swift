import Foundation
import VipiCore
@main struct LocalWordSelectionChecks {
 static func main() throws {
  let text="one two three four five six seven eight"
  let words=[NSRange(location:0,length:3),NSRange(location:4,length:3),NSRange(location:8,length:5),NSRange(location:14,length:4),NSRange(location:19,length:4),NSRange(location:24,length:3),NSRange(location:28,length:5),NSRange(location:34,length:5)]
  typealias S=LocalWordSelection
  func c(_ index:Int,_ face:String,seen:Bool=false,due:Bool=false) -> S.Candidate { .init(range:words[index],surface:face,partOfSpeech:.noun,evidence:.reviewedLexicon,seen:seen,due:due) }
  let novel=[c(0,"one"),c(1,"two"),c(2,"three")], seen=c(3,"four",seen:true,due:true)
  let first=S.select(original:text,nativeWordRanges:words,protectedRanges:[],candidates:novel,density:0.25)!
  precondition(first.novelBudget==2 && first.totalCeiling==6 && first.selected.map(\.surface)==["one","two"])
  let later=S.select(original:text,nativeWordRanges:words,protectedRanges:[],candidates:novel+[seen],density:0.25)!
  precondition(later.selected.map(\.surface)==["one","two","four"])
  let full=S.select(original:text,nativeWordRanges:words,protectedRanges:[],candidates:novel+[seen,c(4,"five",seen:true),c(5,"six",seen:true),c(6,"seven",seen:true),c(7,"eight",seen:true)],density:0.25)!
  precondition(full.selected.count==6 && full.selected.contains(where: {!$0.seen}) && full.selected.contains(where: {$0.due}))
  let protected=S.select(original:text,nativeWordRanges:words,protectedRanges:[words[3]],candidates:novel+[seen],density:0.25)!
  precondition(!protected.selected.contains(where: {$0.surface=="four"}) && protected.rejected["protected_scope"]==1)
  let conflict=S.Candidate(range:words[0],surface:"one",partOfSpeech:.verb,evidence:.nativeTagger)
  let partial=S.Candidate(range:NSRange(location:0,length:2),surface:"on",partOfSpeech:.noun,evidence:.nativeTagger)
  let final=S.select(original:text,nativeWordRanges:words,protectedRanges:[],candidates:novel+[conflict,partial],density:0.25)!
  precondition(final.selected.map(\.surface)==["two","three"] && final.rejected["conflicting_pos"]==2 && final.rejected["source_scope"]==1)
  let phrase=S.Candidate(range:NSRange(location:0,length:7),surface:"one two",partOfSpeech:.noun,evidence:.reviewedLexicon)
  let phraseResult=S.select(original:text,nativeWordRanges:words,protectedRanges:[],candidates:[phrase,seen,c(4,"five")],density:0.25)!
  precondition(phraseResult.selected.map(\.surface)==["one two","four"] && phraseResult.novelBudget==2)
  precondition(S.select(original:text,nativeWordRanges:words,protectedRanges:[],candidates:novel+[seen],density:0)!.selected.isEmpty)
  precondition(S.select(original:text,nativeWordRanges:words,protectedRanges:[],candidates:novel,density:.nan)==nil)
  let tiny=S.select(original:"one two",nativeWordRanges:[NSRange(location:0,length:3),NSRange(location:4,length:3)],protectedRanges:[],candidates:[c(0,"one"),.init(range:NSRange(location:4,length:3),surface:"two",partOfSpeech:.noun,evidence:.nativeTagger,seen:true,due:true)],density:0.25)!
  precondition(tiny.totalCeiling==1 && tiny.selected.map(\.surface)==["one"])
  let identities=try checkFrameIdentities(CommandLine.arguments[1]); precondition(identities==12)
  let policies=try checkAdditiveFixtures(CommandLine.arguments[2]); precondition(policies==13)
  print("PASS: 12 identity vectors; additive seen plus novel budget, total cap, due, zero, protected, conflict, partial and tiny cap")
 }
}
