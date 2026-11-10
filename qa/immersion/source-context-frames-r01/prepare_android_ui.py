#!/usr/bin/env python3
"""Prepare a separate DEBUG host and UI test; no source staging or build."""
from pathlib import Path
import hashlib,json,subprocess,difflib
Q=Path(__file__).resolve().parent;R=Q.parents[2];W=Path('/home/ai/Development/investigations/vipi-source-context-frames-20261109-r01')
def repl(s,a,b):assert s.count(a)==1,a;return s.replace(a,b)
def main():
 hostpath='android/app/src/debug/java/co/fallsoft/vipi/StarterRouteQualificationActivity.kt';testpath='android/app/src/androidTest/java/co/fallsoft/vipi/StarterRouteDeviceTest.kt';manifestpath='android/app/src/debug/AndroidManifest.xml'
 host=subprocess.check_output(['git','show','HEAD:'+hostpath],cwd=R).decode();test=subprocess.check_output(['git','show','HEAD:'+testpath],cwd=R).decode();manifest=subprocess.check_output(['git','show','HEAD:'+manifestpath],cwd=R).decode();oldhost=host;oldtest=test
 host=host.replace('StarterRouteQualificationActivity','FrameRouteQualificationActivity')
 begin=host.index('        val expanded=');end=host.index('        val face=expected',begin)
 host=host[:begin]+'''        val original="We need a phone charger and your phone number."
        val density=.75
        val expected=if(target=="ja")listOf("私たち","携帯電話の充電器","電話番号") else listOf("sisi","chaja ya simu","na","Nambari ya simu")
        val reviewedProvider=createProvider(target)
'''+host[end:]
 host=repl(host,'File(filesDir,"starter-route-ui-${if(expanded) "expanded-" else if(packed) "packed-" else ""}$target")','File(filesDir,"frame-route-ui-$target")')
 host=repl(host,'qaModelsReady=false) }','qaModelsReady=false,sourceKnownConceptIDs=emptySet(),sourceLookup=reviewedProvider) }')
 host=host.replace('.put("packed",packed)','.put("test_only_reference_first_provider",true)')
 host=repl(host,'BundledStarterLookup.provider(this@FrameRouteQualificationActivity)?.cacheIdentity','reviewedProvider.cacheIdentity')
 host=repl(host,'Text("Default source-first chat connection QA")','Text("Private source-context chat connection QA")')
 host=repl(host,'.put("translation_calls",outcome.localTranslationCalls)','.put("translation_calls",outcome.localTranslationCalls).put("routing_branch",routingBranch).put("supplied_target_or_span",false)')
 marker='    override fun onCreate(savedInstanceState:Bundle?) {'
 method='''    private var routingBranch="not_invoked"
    private fun createProvider(target:String):SourceLookupProvider {
        fun read(name:String)=File(filesDir,name).readBytes()
        val manifestBytes=read("manifest.json")
        check(JapaneseStarterLookup.sha(manifestBytes)=="7ebbcfdb1e72290a5fdd1beda5c9c99c1fda1940a92fc1152876e89880cc7896")
        val manifest=JSONObject(manifestBytes.toString(Charsets.UTF_8));val files=manifest.getJSONObject("files")
        for(name in files.keys())check(JapaneseStarterLookup.sha(read(name))==files.getString(name))
        val spec=manifest.getJSONObject("packs").getJSONObject(target)
        val baseline:SourceLookupProvider;val raw:()->List<FrameStarterCandidate>
        if(target=="ja") {
            val x=JapaneseStarterLookup(read(spec.getString("pack")),read(spec.getString("manifest")),emptySet(),true)
            baseline=x;raw={x.rawCandidates}
        } else {
            val x=SwahiliStarterLookup(read(spec.getString("pack")),read(spec.getString("manifest")),emptySet(),true)
            baseline=x;raw={x.rawCandidates}
        }
        val adapter=FrameContextAdapter(read(spec.getString("patterns")),read("permission-proposal.json"),target,baseline.cacheIdentity)
        val identity=adapter.identity+":reference-first-v1";val catalog=BundledImmersionCatalog(this);val expectedTarget=target
        return object:SourceLookupProvider {
            override val cacheIdentity=identity
            override suspend fun lookup(original:String,source:String,target:String,density:Double):SourceLookupEvidence {
                require(source=="en" && target==expectedTarget)
                val b=baseline.lookup(original,source,target,density)
                val reference=catalog.reference(original,source,target)
                routingBranch=if(reference!=null)"existing_forward_reference_baseline_evidence" else "reference_miss_frame_evidence"
                val value=if(reference!=null)b else adapter.resolve(original,density,emptySet(),b,raw())
                return SourceLookupEvidence(value.original,value.source,value.target,identity,value.partial,value.recognitions)
            }
        }
    }
'''
 host=repl(host,marker,method+marker)
 test=test.replace('StarterRouteDeviceTest','FrameRouteDeviceTest').replace('StarterRouteQualificationActivity','FrameRouteQualificationActivity')
 begin=test.index('    @Test fun japaneseDefaultRoute');end=test.index('        val args=',begin)
 test=test[:begin]+'''    @Test fun japaneseFrameRoute()=demonstrate("ja")
    @Test fun swahiliFrameRoute()=demonstrate("sw")
    private fun demonstrate(target:String) {
'''+test[end:]
 test=repl(test,'args.getString(if(expanded) "vipiStarterExpandedUI" else if(packed) "vipiStarterPackedUI" else "vipiStarterRouteUI")','args.getString("vipiFrameRouteUI")')
 test=repl(test,'File(context.filesDir,"starter-route-ui-${if(expanded) "expanded-" else if(packed) "packed-" else ""}$target")','File(context.filesDir,"frame-route-ui-$target")')
 begin=test.index('        val original=');end=test.index('        val scenario=',begin)
 test=test[:begin]+'''        val original="We need a phone charger and your phone number."
        val mixed=if(target=="ja") "watashitachi need a keitai denwa no jūdenki and your denwa bangō." else "sisi need a chaja ya simu na your Nambari ya simu."
'''+test[end:]
 test=test.replace('.putExtra("packed",packed).putExtra("expanded",expanded)','')
 a='if(expanded) "The コーヒー and パン are for 昼食." else if(packed) "My 家族 and my 家族 enjoy ピザ." else "Country 音楽 is fun!"'
 test=repl(test,a,'"私たち need a 携帯電話の充電器 and your 電話番号."')
 test=repl(test,'assertTrue(File(out,"proof.json").exists())','''assertTrue(File(out,"proof.json").exists())
            val proof=JSONObject(File(out,"proof.json").readText());assertEquals(original,proof.getString("original"));assertEquals(.75,proof.getDouble("density"),0.0);assertEquals(if(target=="ja")3 else 4,proof.getJSONArray("spans").length());assertEquals("reference_miss_frame_evidence",proof.getString("routing_branch"));assertFalse(proof.getBoolean("supplied_target_or_span"))''')
 manifest=repl(manifest,'    </application>','        <activity android:name="co.fallsoft.vipi.FrameRouteQualificationActivity" android:exported="false" />\n    </application>')
 dest=W/'android-ui-preparation-r01';dest.mkdir(exist_ok=False)
 for name,s in [('FrameRouteQualificationActivity.kt',host),('FrameRouteDeviceTest.kt',test)]:
  p=Q/name;assert not p.exists();p.write_text(s)
 (dest/'AndroidManifest.xml').write_text(manifest)
 for name,old,new in [('host',oldhost,host),('test',oldtest,test)]: (dest/(name+'.diff')).write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='retained-'+name,tofile='private-frame-'+name)))
 (dest/'source-basis.json').write_text(json.dumps({'committed_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip(),'source_paths':[hostpath,testpath,manifestpath],'canonical_unchanged':True},indent=2)+'\n')
if __name__=='__main__':main()
