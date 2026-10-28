import Foundation

public struct ContextFrame:Sendable {
    public let id:String,meaning:String,sourceLanguage:String,targetLanguage:String,reading:String
    public let sourceParts:[ContextPart],targetParts:[ContextPart]
    public let lexicalUnit:Bool,sourceUnit:Bool,targetUnit:Bool,commonNounCaseVariants:Bool
    public init(id:String,meaning:String,sourceLanguage:String,targetLanguage:String,
                sourceParts:[ContextPart],targetParts:[ContextPart],reading:String="",lexicalUnit:Bool=false,
                sourceUnit:Bool?=nil,targetUnit:Bool?=nil,commonNounCaseVariants:Bool=false) {
        self.id=id;self.meaning=meaning;self.sourceLanguage=sourceLanguage;self.targetLanguage=targetLanguage
        self.sourceParts=sourceParts;self.targetParts=targetParts;self.reading=reading
        self.lexicalUnit=lexicalUnit;self.commonNounCaseVariants=commonNounCaseVariants
        self.sourceUnit=sourceUnit ?? lexicalUnit;self.targetUnit=targetUnit ?? lexicalUnit
    }
}
public struct ContextFrameHit:Sendable {
    public let frame:ContextFrame,sourceWindows:[NSRange],targetWindows:[NSRange]
    public init(frame:ContextFrame,sourceWindows:[NSRange],targetWindows:[NSRange]) {
        self.frame=frame;self.sourceWindows=sourceWindows;self.targetWindows=targetWindows
    }
}

/// Exact indexed phrase matches are structural evidence, not linguistic review.
/// Both sides must match; conflicting source meanings survive a missing target.
public enum ContextFrameMatcher {
    public static func entries(original:String,translation:String,source:String,target:String,hits:[ContextFrameHit]) -> [VocabularyEntry] {
        guard !original.isEmpty,!translation.isEmpty,original.utf16.count<=16384,translation.utf16.count<=32768,
              source != target,hits.count<=256,Set(hits.map{ $0.frame.id }).count==hits.count else {return []}
        var groups:[NSRange:[(ContextFrame,NSRange?)]]=[:];var blocked=Set<NSRange>()
        func focuses(_ text:String,_ windows:[NSRange],_ parts:[ContextPart],_ unit:Bool) -> Set<NSRange>? {
            guard windows.count<=256 else {return nil}
            if unit {
                guard parts.count==1,case .focus(let word)=parts[0],!word.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty,
                      word.utf16.count<=128 else {return nil}
            }
            var result=Set<NSRange>()
            for window in windows {
                guard window.location>=0,window.length>0,window.length<=256,
                      window.location<=text.utf16.count-window.length,Range(window,in:text) != nil else {return nil}
                let fragment=(text as NSString).substring(with:window)
                let focus:NSRange
                if unit {
                    guard case .focus(let word)=parts[0],word==fragment else {return nil}
                    focus=NSRange(location:0,length:fragment.utf16.count)
                } else {
                    guard let matched=ContextMappingMatcher.focus(in:fragment,parts:parts) else {return nil}
                    focus=matched
                }
                result.insert(NSRange(location:window.location+focus.location,length:focus.length))
            }
            return result
        }
        for hit in hits {
            let frame=hit.frame
            guard frame.sourceLanguage==source,frame.targetLanguage==target,!frame.id.isEmpty,frame.id.utf16.count<=256,
                  !frame.meaning.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty,frame.meaning.utf16.count<=2048,
                  frame.lexicalUnit == (frame.sourceUnit && frame.targetUnit),
                  let left=focuses(original,hit.sourceWindows,frame.sourceParts,frame.sourceUnit),!left.isEmpty,
                  let right=focuses(translation,hit.targetWindows,frame.targetParts,frame.targetUnit) else {return []}
            // Identical assessed whole units display the same vocabulary
            // and reading at every occurrence. Only exact equal counts may
            // pair in written order; phrase alignment is not inferred.
            let repeatedUnits=frame.sourceUnit && frame.targetUnit && left.count>1 && left.count==right.count
            // Keep absent aliases as competing meaning evidence, without
            // manufacturing a target-count mismatch for the present alias.
            let absentUnitAlias=frame.sourceUnit && frame.targetUnit && right.isEmpty
            if (left.count>1 || right.count>1) && !repeatedUnits && !absentUnitAlias {blocked.formUnion(left)}
            let orderedTargets=right.sorted{$0.location<$1.location}
            for (index,focus) in left.sorted(by:{$0.location<$1.location}).enumerated() {
                groups[focus,default:[]].append((frame,repeatedUnits ? orderedTargets[index] : (right.count==1 ? right.first : nil)))
            }
        }
        func casePermitted(_ frame:ContextFrame,_ text:String,_ range:NSRange,_ language:String,_ unit:Bool)->Bool {
            let word=(text as NSString).substring(with:range)
            guard frame.commonNounCaseVariants,unit,["en","es","fr","it","pt","sw"].contains(language),
                  word.first?.isUppercase==true else {return true}
            return WrittenCase.sentenceInitial(text,start:range.location)
        }
        var entries:[VocabularyEntry]=[]
        for (focus,group) in groups.sorted(by:{$0.key.location<$1.key.location}) {
            guard !blocked.contains(focus),Set(group.map{$0.0.meaning}).count==1 else {continue}
            for (frame,targetFocus) in group {
                guard let targetFocus else {continue}
                // Native tokenization can split a listed plural suffix. Within
                // this one source focus and assessed sense, retain the complete
                // approved target unit before normal ambiguity checks.
                if frame.targetUnit && group.contains(where: { other, parent in
                    guard other.targetUnit, let parent, parent != targetFocus else { return false }
                    return parent.location <= targetFocus.location && NSMaxRange(parent) >= NSMaxRange(targetFocus)
                }) { continue }
                // Preserve competing meanings and repeated occurrences above;
                // capitalization only vetoes the final candidate.
                guard casePermitted(frame,original,focus,source,frame.sourceUnit),
                      casePermitted(frame,translation,targetFocus,target,frame.targetUnit) else {continue}
                let word=(translation as NSString).substring(with:targetFocus)
                let entry=VocabularyEntry(source:(original as NSString).substring(with:focus),targets:[word],
                    romanizations:frame.reading.isEmpty ? [:] : [word:[frame.reading]],
                    sourceScope:.init(original:original,start:focus.location,end:NSMaxRange(focus)),
                    targetScope:.init(translation:translation,start:targetFocus.location,end:NSMaxRange(targetFocus)))
                if !entries.contains(entry) {entries.append(entry)}
            }
        }
        return entries
    }
}

/// Sentence starts may follow opening punctuation; a mid-sentence quote cannot
/// turn the following capitalized word into a common noun.
public enum WrittenCase {
    public static func sentenceInitial(_ text:String,start:Int)->Bool {
        guard start>=0,start<=text.utf16.count,
              Range(NSRange(location:0,length:start),in:text) != nil else {return false}
        var before=String((text as NSString).substring(to:start))
        while let last=before.last,last.isWhitespace || "¿¡\"'“‘«([{".contains(last) {before.removeLast()}
        return before.isEmpty || ".!?。！？".contains(before.last!)
    }
}
