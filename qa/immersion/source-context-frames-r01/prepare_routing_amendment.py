#!/usr/bin/env python3
"""Create test-only successor harnesses; never overwrite executed sources or inputs."""
from pathlib import Path
import json,hashlib,shutil
Q=Path(__file__).resolve().parent;W=Path('/home/ai/Development/investigations/vipi-source-context-frames-20261109-r01')
def replace(s,a,b):assert s.count(a)==1,a;return s.replace(a,b)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 kt=(Q/'SourceContextFrameTest.kt').read_text().replace('class SourceContextFrameTest','class SourceContextFrameRoutingTest')
 kt=replace(kt,'val cases=JSONObject(read("cases.json")','val previous=read("prior-android-output.jsonl").toString(Charsets.UTF_8).lineSequence().filter{it.isNotBlank()}.map{JSONObject(it)}.toList();check(previous.size==656)\n  val cases=JSONObject(read("cases.json")')
 kt=replace(kt,'val expectedTarget=target','val expectedTarget=target') if False else kt
 kt=replace(kt,'val provider=object:SourceLookupProvider {override val cacheIdentity=adapter.identity;override suspend fun lookup(original:String,source:String,target:String,density:Double):SourceLookupEvidence {\n     require(source=="en" && target==expectedTarget);val b=x.provider.lookup(original,source,target,density);return adapter.resolve(original,density,known,b,x.raw())\n    }}','''val routingIdentity=adapter.identity+":reference-first-v1"
    val catalogStarted=SystemClock.elapsedRealtimeNanos();val referenceCatalog=BundledImmersionCatalog(context);val catalogSetupMs=(SystemClock.elapsedRealtimeNanos()-catalogStarted)/1e6
    var referenceCalls=0;var branch="not_invoked";var referenceMs:Double?=null;var referenceFirst=false
    fun envelope(v:SourceLookupEvidence)=SourceLookupEvidence(v.original,v.source,v.target,routingIdentity,v.partial,v.recognitions)
    val provider=object:SourceLookupProvider {override val cacheIdentity=routingIdentity;override suspend fun lookup(original:String,source:String,target:String,density:Double):SourceLookupEvidence {
     require(source=="en" && target==expectedTarget);val b=x.provider.lookup(original,source,target,density)
     val start=SystemClock.elapsedRealtimeNanos();val reference=referenceCatalog.reference(original,source,target);referenceMs=(SystemClock.elapsedRealtimeNanos()-start)/1e6;referenceFirst=referenceCalls++==0
     branch=if(reference!=null)"existing_forward_reference_baseline_evidence" else "reference_miss_frame_evidence"
     return envelope(if(reference!=null)b else adapter.resolve(original,density,known,b,x.raw()))
    }}''')
 kt=replace(kt,'val raw=JSONArray(x.trace().toString());val candidate=adapter.resolve(text,d,known,b,x.raw());val frameTrace=JSONArray(adapter.trace.toString())','''val raw=JSONArray(x.trace().toString());val directStart=SystemClock.elapsedRealtimeNanos();val candidate=adapter.resolve(text,d,known,b,x.raw());val directMs=(SystemClock.elapsedRealtimeNanos()-directStart)/1e6;val frameTrace=JSONArray(adapter.trace.toString())
     val prior=previous.single{it.getString("pair")=="en-"+target && it.getString("id")==c.getString("id") && it.getString("state")==state && it.getDouble("density")==d}
     assertEquals(prior.getJSONObject("baseline").toString(),evidence(b).toString());assertEquals(prior.getJSONObject("candidate").toString(),evidence(candidate).toString());assertEquals(prior.getJSONArray("starter_trace").toString(),raw.toString());assertEquals(prior.getJSONArray("frame_trace").toString(),frameTrace.toString())''')
 kt=replace(kt,'val route=JSONObject()','val route=JSONObject();val timing=JSONObject().put("direct_resolve_ms",directMs).put("reference_catalog_constructor_ms",catalogSetupMs).put("fresh_engine_per_route",true)')
 kt=replace(kt,'val engine=ConversationImmersion(context,','val setupStart=SystemClock.elapsedRealtimeNanos();val engine=ConversationImmersion(context,')
 kt=replace(kt,'try {val id=state+', 'val setupMs=(SystemClock.elapsedRealtimeNanos()-setupStart)/1e6\n      try {val id=state+')
 kt=replace(kt,'val value=engine.presentation(text,"en",id);','val callStart=SystemClock.elapsedRealtimeNanos();val value=engine.presentation(text,"en",id);val elapsedMs=(SystemClock.elapsedRealtimeNanos()-callStart)/1e6;timing.put(arm+"_setup_ms",setupMs).put(arm+"_result_ms",elapsedMs);')
 kt=replace(kt,'     write(JSONObject().put("pair"','''     assertEquals(prior.getJSONObject("route").getJSONObject("baseline").toString(),route.getJSONObject("baseline").toString())
     if(branch=="existing_forward_reference_baseline_evidence")assertEquals(route.getJSONObject("baseline").toString(),route.getJSONObject("candidate").toString())
     else assertEquals(prior.getJSONObject("route").getJSONObject("candidate").toString(),route.getJSONObject("candidate").toString())
     timing.put("reference_lookup_ms",referenceMs?:JSONObject.NULL).put("first_reference_lookup_for_pair_state",referenceFirst)
     write(JSONObject().put("routing_branch",branch).put("timing",timing).put("pair"''')
 sw=(Q/'SourceContextFrameTests.swift').read_text().replace('class SourceContextFrameTests','class SourceContextFrameRoutingTests')
 sw=replace(sw,'let cases=try json("cases.json")','let previous=try String(decoding:read("prior-apple-output.jsonl"),as:UTF8.self).split(separator:"\\n").map{try XCTUnwrap(JSONSerialization.jsonObject(with:Data($0.utf8)) as? [String:Any])};guard previous.count==656 else {throw Failed.prerequisite}\n        let cases=try json("cases.json")')
 sw=replace(sw,'let provider=SourceUnitLookup(identity:adapter.identity){request in\n                    let b=try await x.provider.resolve(request)\n                    return try adapter.resolve(original:request.original,density:request.density,known:request.knownConceptIDs,baseline:b,raw:x.raw())\n                }','''let routingIdentity=adapter.identity+":reference-first-v1"
                let catalogStart=ProcessInfo.processInfo.systemUptime,referenceCatalog=BundledImmersionCatalog()
                let catalogSetupMs=(ProcessInfo.processInfo.systemUptime-catalogStart)*1000
                var referenceCalls=0,branch="not_invoked";var referenceMs:Double?;var referenceFirst=false
                let provider=SourceUnitLookup(identity:routingIdentity){request in
                    let b=try await x.provider.resolve(request)
                    let start=ProcessInfo.processInfo.systemUptime
                    let reference=try await referenceCatalog.reference(original:request.original,pair:request.pair)
                    referenceMs=(ProcessInfo.processInfo.systemUptime-start)*1000;referenceFirst=referenceCalls==0;referenceCalls+=1
                    branch=reference != nil ? "existing_forward_reference_baseline_evidence" : "reference_miss_frame_evidence"
                    let value:SourceLookupEvidence
                    if reference != nil {value=b} else {value=try adapter.resolve(original:request.original,density:request.density,known:request.knownConceptIDs,baseline:b,raw:x.raw())}
                    return SourceLookupEvidence(original:value.original,source:value.source,target:value.target,catalogIdentity:routingIdentity,partial:value.partial,recognitions:value.recognitions)
                }''')
 sw=replace(sw,'let raw=x.trace(),candidate=try adapter.resolve(original:text,density:d,known:known,baseline:b,raw:x.raw()),frameTrace=adapter.trace','''let raw=x.trace(),directStart=ProcessInfo.processInfo.systemUptime
                        let candidate=try adapter.resolve(original:text,density:d,known:known,baseline:b,raw:x.raw()),directMs=(ProcessInfo.processInfo.systemUptime-directStart)*1000,frameTrace=adapter.trace
                        let prior=try XCTUnwrap(previous.first{($0["pair"] as? String)=="en-"+target && ($0["id"] as? String)==id && ($0["state"] as? String)==state && ($0["density"] as? Double)==d})
                        try same(encoded(XCTUnwrap(prior["baseline"])),encoded(evidence(b)));try same(encoded(XCTUnwrap(prior["candidate"])),encoded(evidence(candidate)));try same(encoded(XCTUnwrap(prior["starter_trace"])),encoded(raw));try same(encoded(XCTUnwrap(prior["frame_trace"])),encoded(frameTrace))''')
 sw=replace(sw,'var route:[String:Any]=[:]','var route:[String:Any]=[:];var timing:[String:Any]=["direct_resolve_ms":directMs,"reference_catalog_constructor_ms":catalogSetupMs,"fresh_engine_per_route":true]')
 sw=replace(sw,'let engine=ConversationImmersion(modelStatus:', 'let setupStart=ProcessInfo.processInfo.systemUptime\n                            let engine=ConversationImmersion(modelStatus:')
 sw=replace(sw,'let value=await engine.result(for:text,inputLanguage:"en",messageID:message);','let setupMs=(ProcessInfo.processInfo.systemUptime-setupStart)*1000,callStart=ProcessInfo.processInfo.systemUptime\n                            let value=await engine.result(for:text,inputLanguage:"en",messageID:message);timing[arm+"_setup_ms"]=setupMs;timing[arm+"_result_ms"]=(ProcessInfo.processInfo.systemUptime-callStart)*1000;')
 sw=replace(sw,'try write(["pair":"en-"+target','''let priorRoute=try XCTUnwrap(prior["route"] as? [String:Any])
                        try same(encoded(XCTUnwrap(priorRoute["baseline"])),encoded(XCTUnwrap(route["baseline"])))
                        if branch=="existing_forward_reference_baseline_evidence" {try same(encoded(XCTUnwrap(route["baseline"])),encoded(XCTUnwrap(route["candidate"])))}
                        else {try same(encoded(XCTUnwrap(priorRoute["candidate"])),encoded(XCTUnwrap(route["candidate"])))}
                        timing["reference_lookup_ms"]=referenceMs as Any? ?? NSNull();timing["first_reference_lookup_for_pair_state"]=referenceFirst
                        try write(["routing_branch":branch,"timing":timing,"pair":"en-"+target''')
 kt=kt.replace('val route=JSONObject();val timing=', 'branch=\"not_invoked\";referenceMs=null;referenceFirst=false\n     val route=JSONObject();val timing=')
 sw=sw.replace('var route:[String:Any]=[:];var timing:', 'branch=\"not_invoked\";referenceMs=nil;referenceFirst=false\n                        var route:[String:Any]=[:];var timing:')
 for name,text in [('SourceContextFrameRoutingTest.kt',kt),('SourceContextFrameRoutingTests.swift',sw)]:
  p=Q/name;assert not p.exists();p.write_text(text)
 dest=W/'native-inputs-r03';assert not dest.exists();shutil.copytree(W/'native-inputs-r02',dest)
 manifest=json.loads((dest/'manifest.json').read_text());manifest['parent_manifest_sha256']=sha(W/'native-inputs-r02/manifest.json')
 for platform,path in [('android',W/'android-capture-r01/output.stdout'),('apple',W/'apple-run-r01/inputs-r02/frame-output.jsonl')]:
  name='prior-'+platform+'-output.jsonl';shutil.copyfile(path,dest/name);manifest['files'][name]=sha(dest/name)
 (dest/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 print(json.dumps({'manifest_sha256':sha(dest/'manifest.json'),'files':{n:sha(Q/n) for n in ['SourceContextFrameRoutingTest.kt','SourceContextFrameRoutingTests.swift']}},indent=2))
if __name__=='__main__':main()
