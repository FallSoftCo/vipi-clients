    // RESEARCH ONLY: target evidence defers global source-entry/sense rejection.
    // All exact edges remain competing claims, including non-display owners.
    private static func targetInformedEntries(left:Side,right:Side,original:String,translation:String,
        source:String,target:String,alignment:SentenceAlignment,diagnostic:(String)->Void) throws -> [VocabularyEntry] {
        struct Edge:Hashable { let source:NSRange,target:NSRange,reading:String }
        var edges=Set<Edge>(),display=Set<Edge>()
        let needsReading=["ar","zh","ja","ko"].contains(target)
        func log(_ value:[String:Any]) {
            if let data=try? JSONSerialization.data(withJSONObject:value,options:[.sortedKeys]),let text=String(data:data,encoding:.utf8) {diagnostic("target_graph:"+text)}
        }
        for word in left.forms.keys.sorted() {
            let forms=left.forms[word,default:[]]
            // Inventory first: absent/unusable relations never disappear from audit.
            for form in forms {
                log(["kind":"source_analysis","key":word,"lexeme":form.lexeme,"mode":form.mode,"source_safe":form.sourceSafe,
                     "terms":linkedTerms(left,form).map{["sense":$0.sense,"eligible":$0.eligible,"explicit":$0.explicit]}])
            }
            guard !left.blocked.contains(word) else {diagnostic("source_guard");continue}
            for form in Set(forms) {
                guard (1...3).contains(form.mode) else {diagnostic("unusable_source_form_retained");continue}
                let meanings=Set(linkedTerms(left,form).filter{$0.eligible && (source=="en" || target=="en" || $0.explicit)}.map(\.sense))
                guard !meanings.isEmpty else {diagnostic("unlinked_source_analysis_retained");continue}
                let features=forms.filter{$0.lexeme==form.lexeme && $0.mode==form.mode}.map(\.features).reduce(form.features){$0.intersection($1)}
                for carrier in Set(left.windows[word,default:[]]) {
                    guard !protected(left,range:carrier),targetCaseMatches(form,range:carrier,text:original),
                          let sf=sourceFocus(form,range:carrier,text:original),sf==carrier else {continue}
                    let uniqueSource=alignment.uniqueSource(carrier,left.windows[word,default:[]].filter{!protected(left,range:$0)})
                    for other in right.forms.keys.sorted() {
                        guard !right.targetBlocked.contains(other) else {continue}
                        let targets=right.forms[other,default:[]]
                        for tf in Set(targets) {
                            let shared=Set(linkedTerms(right,tf).filter{$0.eligible && meanings.contains($0.sense)}.map(\.sense))
                            guard !shared.isEmpty else {continue}
                            let rr=readings(right,tf,shared)
                            guard tf.targetSafe,!(tf.features.contains("abbreviation") && targets.contains{$0.grammar}),
                                  (1...3).contains(tf.mode),numberCompatible(form,tf,source:source,target:target) else {
                                log(["kind":"pair_form_rejection","source_lexeme":form.lexeme,"target_lexeme":tf.lexeme,"shared":shared.sorted(),"source_number":form.number,"target_number":tf.number,"target_mode":tf.mode]);continue
                            }
                            for tc in Set(right.windows[other,default:[]]) {
                                guard !protectedTarget(right,range:tc,text:translation,language:target,features:features),
                                      targetCaseMatches(tf,range:tc,text:translation),let targetFocus=focus(tf,range:tc,text:translation),
                                      alignment.permits(sf,targetFocus) else {continue}
                                // For ES reading is empty. For reading languages retain all alternatives;
                                // no reading/ambiguous readings can block but never display.
                                let readingsToKeep=needsReading ? (rr.isEmpty ? Set([""]) : rr) : Set([""])
                                for reading in readingsToKeep {
                                    let e=Edge(source:sf,target:targetFocus,reading:reading);edges.insert(e)
                                    let canDisplay=uniqueSource && form.targetSafe && !form.proper && !form.grammar && !left.names.contains(word) && (!needsReading || rr.count==1 && !reading.isEmpty)
                                    if canDisplay {display.insert(e)}
                                    log(["kind":"edge","source_lexeme":form.lexeme,"target_lexeme":tf.lexeme,"source":[sf.location,NSMaxRange(sf)],"target":[targetFocus.location,NSMaxRange(targetFocus)],"shared":shared.sorted(),"display_form":canDisplay])
                                    guard edges.count<=8192 else {throw Limit.overflow}
                                }
                            }
                        }
                    }
                }
            }
        }
        // Include target analyses lacking a matching source link in the audit too.
        for key in right.forms.keys.sorted() {for f in right.forms[key,default:[]] {
            log(["kind":"target_analysis","key":key,"lexeme":f.lexeme,"mode":f.mode,"terms":linkedTerms(right,f).map{["sense":$0.sense,"eligible":$0.eligible]}])
        }}
        func unique(_ e:Edge)->Bool {
            !edges.contains { other in
                (other.source==e.source && (other.target != e.target || other.reading != e.reading)) ||
                (NSIntersectionRange(other.source,e.source).length==0 && NSIntersectionRange(other.target,e.target).length>0)
            }
        }
        var result:[VocabularyEntry]=[]
        for e in edges.sorted(by:{a,b in
            if a.source.location != b.source.location {return a.source.location<b.source.location}
            if a.source.length != b.source.length {return a.source.length<b.source.length}
            if a.target.location != b.target.location {return a.target.location<b.target.location}
            if a.target.length != b.target.length {return a.target.length<b.target.length}
            return a.reading<b.reading
        }) {
            let admitted=display.contains(e) && unique(e)
            let targetText=(translation as NSString).substring(with:e.target)
            // requiresContext with no hints is deliberately claim-only. It reaches
            // existing competing-claim checks but cannot itself emit a display.
            result.append(VocabularyEntry(source:(original as NSString).substring(with:e.source),targets:[targetText],
                romanizations:needsReading && !e.reading.isEmpty ? [targetText:[e.reading]] : [:],requiresContext:!admitted,
                sourceScope:VocabularySourceScope(original:original,start:e.source.location,end:NSMaxRange(e.source)),
                targetScope:VocabularyTargetScope(translation:translation,start:e.target.location,end:NSMaxRange(e.target))))
            log(["kind":"ownership","source":[e.source.location,NSMaxRange(e.source)],"target":[e.target.location,NSMaxRange(e.target)],"admitted":admitted])
        }
        return result
    }
