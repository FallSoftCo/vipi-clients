import Foundation
import NaturalLanguage
import VipiCore

/// The original-source range actually translated, not a guessed target word span.
struct ManualSourceContext: Sendable {let text:String,startUTF16:Int,endUTF16:Int}
enum ManualTranslationContext {
    private static let closing=Set(")]}'\"”’»〉」』】〕〗）］｝".utf16)
    private static let terminal=Set(".!?…。！？؟".utf16)
    private static let abbreviations=#"(?i)(?:\b(?:mr|mrs|ms|dr|prof|sr|jr|st|vs|etc|fig|no|m|mme|mlle|sig|dott|sra)|(?:\b\p{L}\.)+\p{L}|\b\p{L})\.$"#
    static func enclosing(_ text:String,start:Int,end:Int,language:String?)->ManualSourceContext {
        let native=text as NSString
        func whole()->ManualSourceContext {.init(text:text,startUTF16:0,endUTF16:native.length)}
        guard start>=0,end>start,end<=native.length else{return whole()}
        if start==0,end==native.length{return whole()}
        var characterBoundaries:Set<Int>=[0],offset=0
        for character in text {offset+=String(character).utf16.count;characterBoundaries.insert(offset)}
        let protected=TranslationIntegrity.protectedLiteralRanges(text)
        func insideLiteral(_ position:Int)->Bool {protected.contains{position>$0.location && position<NSMaxRange($0)}}
        func whitespace(_ position:Int)->Bool {Unicode.Scalar(native.character(at:position)).map{CharacterSet.whitespacesAndNewlines.contains($0)}==true}
        var boundaries:Set<Int>=[0,native.length]
        let tokenizer=NLTokenizer(unit:.sentence);tokenizer.string=text
        if let language {tokenizer.setLanguage(NLLanguage(rawValue:language))}
        tokenizer.enumerateTokens(in:text.startIndex..<text.endIndex){range,_ in
            var candidate=NSMaxRange(NSRange(range,in:text))
            while candidate>0 && whitespace(candidate-1){candidate-=1}
            while candidate<native.length && closing.contains(native.character(at:candidate)){candidate+=1}
            if candidate>0,candidate<native.length,characterBoundaries.contains(candidate),!insideLiteral(candidate){
                var punctuation=candidate
                while punctuation>0 && closing.contains(native.character(at:punctuation-1)){punctuation-=1}
                let complete=punctuation>0 && terminal.contains(native.character(at:punctuation-1))
                let prefix=native.substring(to:punctuation)
                if complete,prefix.range(of:abbreviations,options:.regularExpression)==nil {boundaries.insert(candidate)}
            }
            return true
        }
        var from=boundaries.filter{$0<=start}.max() ?? 0,to=boundaries.filter{$0>=end}.min() ?? native.length
        while from<start && whitespace(from){from+=1}
        while to>end && whitespace(to-1){to-=1}
        guard from<=start,to>=end,from<to,characterBoundaries.contains(from),characterBoundaries.contains(to),!insideLiteral(from),!insideLiteral(to) else{return whole()}
        let pairs:[UInt16:UInt16]=[40:41,91:93,123:125,0x201c:0x201d,0xab:0xbb,0x300c:0x300d,0x300e:0x300f]
        var stack:[UInt16]=[],quotes=false
        for i in from..<to {
            if protected.contains(where:{NSLocationInRange(i,$0)}){continue}
            let c=native.character(at:i)
            if c==34{quotes.toggle()}
            if let close=pairs[c]{stack.append(close)}
            else if pairs.values.contains(c){guard stack.popLast()==c else{return whole()}}
        }
        guard stack.isEmpty,!quotes else{return whole()}
        return .init(text:native.substring(with:NSRange(location:from,length:to-from)),startUTF16:from,endUTF16:to)
    }
}
