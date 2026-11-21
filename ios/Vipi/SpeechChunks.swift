import Foundation
import NaturalLanguage

enum SpeechChunks {
    /// Two adjacent immersion units may have no separator in the original
    /// script. Keep their utterances distinct instead of synthesizing a new
    /// joined word (for example, English “togetherlunch” from Japanese slots).
    /// Whitespace and punctuation already supply a natural joining boundary.
    static func coalesced(_ spans: [(text: String, language: String)]) -> [(text: String, language: String)] {
        var result: [(text: String, language: String)] = []
        for span in spans {
            guard !span.text.isEmpty else { continue }
            let punctuationOnly = span.text.allSatisfy { $0.isWhitespace || ".,!?;:。！？、؛،".contains($0) }
            if let last = result.last {
                let touchingLetters = last.text.last?.isLetter == true && span.text.first?.isLetter == true
                if punctuationOnly || (last.language == span.language && !touchingLetters) {
                    result[result.count - 1].text += span.text
                    continue
                }
            }
            if !span.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { result.append(span) }
        }
        return result
    }
    /// Linear bounded lookahead; String.count on each remaining suffix makes
    /// large messages quadratic. Never cut a grapheme or discard source tails.
    static func plan(_ spans:[(text:String,language:String)]) -> [[(text:String,language:String)]] {
        plan(spans,checkCancellation:{})
    }
    static func plan(_ spans: [(text: String, language: String)],
                     checkCancellation: () throws -> Void) rethrows -> [[(text: String, language: String)]] {
        var chunks: [[(text:String,language:String)]] = []
        var current: [(text:String,language:String)] = [], count = 0
        for span in spans {
            var start = span.text.startIndex
            while start < span.text.endIndex {
                try checkCancellation()
                var end = start, length = 0, boundary: (String.Index,Int)?
                while end < span.text.endIndex && length < 160 {
                    let character = span.text[end]
                    end = span.text.index(after:end); length += 1
                    if length >= 60 && (character.isWhitespace || ".!?。！？،,;；".contains(character)) { boundary = (end,length) }
                }
                if end != span.text.endIndex,let preferred = boundary { end = preferred.0; length = preferred.1 }
                if count > 0 && count + length > 160 { chunks.append(current); current = []; count = 0 }
                current.append((String(span.text[start..<end]),span.language)); count += length
                start = end
            }
        }
        if !current.isEmpty { chunks.append(current) }
        return chunks
    }
    static func wordRanges(_ text:String,language:String) -> [NSRange] {
        let tokenizer = NLTokenizer(unit:.word)
        tokenizer.string = text; tokenizer.setLanguage(NLLanguage(rawValue:language))
        var ranges:[NSRange] = []
        tokenizer.enumerateTokens(in:text.startIndex..<text.endIndex) { range,_ in
            if hasSpokenContent(String(text[range])) { ranges.append(NSRange(range,in:text)) }
            return true
        }
        return ranges
    }
    static func marksCoverWords(_ marks:[SpeechMark],text:String,language:String) -> Bool {
        let words = wordRanges(text,language:language)
        guard !words.isEmpty,!marks.isEmpty else { return false }
        let offsets = marks.sorted{$0.start < $1.start}.map(\.byteSampleOffset)
        guard zip(offsets,offsets.dropFirst()).allSatisfy({$0.0 < $0.1}) else { return false }
        let ranges = marks.filter{$0.start >= 0 && $0.start <= text.utf16.count && $0.length > 0 && $0.length <= text.utf16.count-$0.start}.map{NSRange(location:$0.start,length:$0.length)}.sorted{$0.location < $1.location}
        return words.allSatisfy { word in
            var cursor = word.location
            for range in ranges where NSIntersectionRange(range,word).length > 0 {
                guard range.location <= cursor else { return false }
                cursor = max(cursor,NSMaxRange(range))
                if cursor >= NSMaxRange(word) { return true }
            }
            return false
        }
    }
    /// Keep each native sentence intact for continuous prosody. The bounded
    /// source-message budget and synthesis timeout still apply to long sentences.
    static func sentencePlan(_ spans:[(text:String,language:String)]) -> [[(text:String,language:String)]] {
        var result:[[(text:String,language:String)]] = []
        for span in spans {
            var cursor = span.text.startIndex
            span.text.enumerateSubstrings(in:span.text.startIndex..<span.text.endIndex,options:.bySentences) { _,_,enclosing,_ in
                guard enclosing.upperBound > cursor else { return }
                result.append([(String(span.text[cursor..<enclosing.upperBound]),span.language)])
                cursor = enclosing.upperBound
            }
            if cursor < span.text.endIndex { result.append([(String(span.text[cursor...]),span.language)]) }
        }
        return result
    }
    static func hasSpokenContent(_ text:String) -> Bool {
        text.unicodeScalars.contains { CharacterSet.alphanumerics.contains($0) }
    }
}

/// Maps the native script onto the actual audio. Missing timestamps affect only
/// visual highlighting. PCM is never split or resynthesized for this purpose.
enum SpeechWordTiming {
    struct VoicedRegion { let start: Int; let end: Int }
    static func regions(energy:[Float], window:Int, frames:Int, sampleRate:Double) -> [VoicedRegion] {
        guard frames > 0,window > 0,sampleRate > 0,let peak=energy.max(),peak > 0 else { return [] }
        let floor = peak * 0.012
        let pause = Int(sampleRate * 0.15)
        var result:[VoicedRegion] = [], start:Int?,end=0
        for (i,value) in energy.enumerated() where value > floor {
            let frame=i*window
            if let previous=start,frame-end >= pause {
                result.append(.init(start:previous,end:end)); start=nil
            }
            if start == nil { start=frame }
            end=min(frames,frame+window)
        }
        if let start,end>start { result.append(.init(start:start,end:end)) }
        return result
    }

    static func interpolate(text:String,language:String,marks:[SpeechMark],regions:[VoicedRegion],
                            frames:Int,bytesPerFrame:Int,sampleRate:Double) -> [SpeechMark] {
        let words=SpeechChunks.wordRanges(text,language:language)
        guard !words.isEmpty,let first=regions.first,let last=regions.last,bytesPerFrame>0,frames>=words.count else { return [] }
        let ns=text as NSString
        let weights=words.map { range in 0.55 + sqrt(Double(ns.substring(with:range).count)) }
        let byStart=Dictionary(uniqueKeysWithValues:words.enumerated().map { ($0.element.location,$0.offset) })
        var anchors:[Int:Int]=[:],native:[Int:SpeechMark]=[:],previousIndex = -1,previousFrame = -1
        for mark in marks.sorted(by:{$0.byteSampleOffset < $1.byteSampleOffset}) {
            guard let i=byStart[mark.start],mark.length>0,mark.length<=ns.length-mark.start,
                  i>previousIndex,mark.byteSampleOffset>=0 else { continue }
            let frame=mark.byteSampleOffset/bytesPerFrame
            guard frame>=previousFrame+(i-previousIndex),frame<frames-(words.count-1-i) else { continue }
            anchors[i]=frame;native[i]=mark;previousFrame=frame;previousIndex=i
        }
        if anchors[0]==nil { anchors[0]=min(first.start,anchors.map{$0.value-$0.key}.min() ?? first.start) }
        anchors[words.count]=max(last.end,(anchors.map{$0.value+words.count-$0.key}.max() ?? 0))
        let sorted=anchors.keys.sorted()
        var starts=anchors
        for (left,right) in zip(sorted,sorted.dropFirst()) where right>left+1 {
            let lo=anchors[left]!,hi=anchors[right]!
            let audible=regions.compactMap { r -> VoicedRegion? in
                let a=max(lo,r.start),b=min(hi,r.end)
                return a<b ? .init(start:a,end:b) : nil
            }
            let duration=audible.reduce(0){$0+$1.end-$1.start}
            let total=weights[left..<right].reduce(0,+)
            var weight=0.0,prev=lo
            for i in (left+1)..<right {
                weight+=weights[i-1]
                var target=lo+Int(Double(hi-lo)*weight/total)
                var offset=Int(Double(duration)*weight/total)
                for region in audible {
                    if offset<region.end-region.start { target=region.start+offset;break }
                    offset-=region.end-region.start
                }
                let tail=NSMaxRange(words[i-1]),gap=NSRange(location:tail,length:words[i].location-tail)
                if ns.substring(with:gap).rangeOfCharacter(from:CharacterSet(charactersIn:",;:.!?，；：。！？،؛؟…")) != nil,
                   let pause=audible.dropFirst().min(by:{abs($0.start-target)<abs($1.start-target)}),
                   Double(abs(pause.start-target)) <= sampleRate*0.24 { target=pause.start }
                target=max(prev+1,min(hi-(right-i),target));starts[i]=target;prev=target
            }
        }
        return words.indices.compactMap { i in
            guard let begin=starts[i],let next=starts[i+1],begin>=0,next>begin else{return nil}
            // Drop the highlight across a material pause even when a later word
            // begins at an OS timestamp rather than an interpolated one.
            let end=regions.first(where:{$0.start<next && $0.end>begin}).map{min(next,$0.end)} ?? next
            return .init(start:words[i].location,length:words[i].length,byteSampleOffset:begin*bytesPerFrame,
                         source:native[i] == nil ? "interpolated_pcm" : "native_anchor",endByteSampleOffset:max(begin+1,end)*bytesPerFrame)
        }
    }
}
