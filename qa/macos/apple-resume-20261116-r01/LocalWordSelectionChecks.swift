import Foundation
import VipiCore
@main struct LocalWordSelectionChecks {
 static func main() {
  let text="I train near bank."
  let words=[NSRange(location:0,length:1),NSRange(location:2,length:5),NSRange(location:8,length:4),NSRange(location:13,length:4)]
  typealias S=LocalWordSelection
  let train=S.Candidate(range:words[1],surface:"train",partOfSpeech:.verb,evidence:.nativeTagger)
  let bank=S.Candidate(range:words[3],surface:"bank",partOfSpeech:.noun,evidence:.reviewedLexicon,due:true)
  let first=S.select(original:text,nativeWordRanges:words,protectedRanges:[],candidates:[train,bank],density:0.25)!
  precondition(first.budget==1 && first.selected.count==1 && first.selected[0].surface=="bank")
  let protected=S.select(original:text,nativeWordRanges:words,protectedRanges:[words[3]],candidates:[train,bank],density:0.25)!
  precondition(protected.selected.count==1 && protected.selected[0].surface=="train" && protected.rejected["protected_scope"]==1)
  let conflict=S.Candidate(range:words[1],surface:"train",partOfSpeech:.noun,evidence:.reviewedLexicon)
  let bad=S.Candidate(range:NSRange(location:2,length:4),surface:"trai",partOfSpeech:.verb,evidence:.nativeTagger)
  let duplicate=S.Candidate(range:words[3],surface:"bank",partOfSpeech:.noun,evidence:.nativeTagger)
  let final=S.select(original:text,nativeWordRanges:words,protectedRanges:[],candidates:[train,conflict,bad,bank,duplicate],density:1)!
  precondition(final.selected.count==1 && final.selected[0].surface=="bank" && final.rejected["conflicting_pos"]==2 && final.rejected["source_scope"]==1 && final.rejected["overlap"]==1)
  precondition(S.select(original:text,nativeWordRanges:words,protectedRanges:[],candidates:[train],density:0)!.selected.isEmpty)
  precondition(S.select(original:text,nativeWordRanges:words,protectedRanges:[],candidates:[train],density:.nan)==nil)
  print("PASS: due budget, protected span, conflicting POS, partial token, duplicate and invalid density")
 }
}
