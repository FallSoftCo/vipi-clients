import Foundation
import VipiCore

/// Decoded only from a verified context pack. Matching creates ephemeral scopes;
/// deserializing a generic vocabulary entry can never grant them.
enum ReviewedContextRecord {
    static func mapping(_ data:Data,source:String,target:String) throws -> ContextMapping {
        struct Row:Decodable {
            let id:String,meaning:String,source_language:String,target_language:String
            let parts:[[String:Part]],target:String,reading:String,target_context:String,target_span:[Int]
            enum Part:Decodable {
                case text(String),slot([String])
                init(from decoder:Decoder) throws {
                    let value=try decoder.singleValueContainer()
                    if let text=try? value.decode(String.self) {self = .text(text)}
                    else {self = .slot(try value.decode([String].self))}
                }
            }
        }
        guard data.count<=32768 else {throw VocabularyPackError.invalid}
        let row=try JSONDecoder().decode(Row.self,from:data)
        guard row.source_language==source,row.target_language==target,row.target_span.count==2 else {throw VocabularyPackError.invalid}
        let a=row.target_span[0],b=row.target_span[1]
        guard a>=0,b>a,b<=row.target_context.utf16.count else {throw VocabularyPackError.invalid}
        let focus=NSRange(location:a,length:b-a)
        guard Range(focus,in:row.target_context) != nil,(row.target_context as NSString).substring(with:focus)==row.target else {throw VocabularyPackError.invalid}
        let parts=try row.parts.map { part -> ContextPart in
            guard part.count==1,let (key,value)=part.first else {throw VocabularyPackError.invalid}
            switch (key,value) {
            case ("literal",.text(let text)):return .literal(text)
            case ("focus",.text(let text)):return .focus(text)
            case ("slot",.slot(let values)):return .slot(values)
            default:throw VocabularyPackError.invalid
            }
        }
        let touching=LocalImmersion.words(row.target_context,language:target).filter{NSIntersectionRange($0,focus).length>0}
        var forms:[VocabularyTargetForm]=[]
        if let first=touching.first,let last=touching.last {
            let start=min(a,first.location),end=max(b,NSMaxRange(last))
            forms=[.init(surface:(row.target_context as NSString).substring(with:NSRange(location:start,length:end-start)),target:row.target,start:a-start,end:b-start)]
        }
        return ContextMapping(id:row.id,meaning:row.meaning,sourceLanguage:source,targetLanguage:target,parts:parts,
            targets:[row.target],readings:row.reading.isEmpty ? [:] : [row.target:[row.reading]],targetForms:forms)
    }
}
