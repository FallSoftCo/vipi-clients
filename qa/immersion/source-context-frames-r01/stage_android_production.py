#!/usr/bin/env python3
from pathlib import Path
import json,hashlib,shutil
Q=Path(__file__).resolve().parent;R=Q.parents[2];W=Path('/home/ai/Development/investigations/vipi-source-context-frames-20261109-r01');S=Path('/home/ai/Development/investigations/vipi-android-source-context-integration-20261109-r01/source');sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 out=W/'android-production-stage-r01.json';assert not out.exists()
 freeze=json.loads((W/'android-production-freeze-r01.json').read_text())
 for name,h in freeze['files'].items():assert sha(Path(name))==h,name
 parent=json.loads((W/'android-ui-stage-r02.json').read_text());after=parent['after'].copy()
 for name,h in after.items():assert sha(S/name)==h,name
 backup=W/'android-production-prior-source-r01';assert not backup.exists();backup.mkdir();delta={}
 def put(name,text):
  p=S/name;before=sha(p) if p.exists() else None
  if p.exists():b=backup/name;b.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,b)
  p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text);after[name]=sha(p);delta[name]={'before':before,'after':sha(p)}
 app='android/app/src/main/java/co/fallsoft/vipi/'
 for name in ['SourceFrameLookup.kt','JapaneseStarterLookup.kt','SwahiliStarterLookup.kt']:
  s=(R/app/name).read_text()
  if name=='SourceFrameLookup.kt':assert s.count('const val PROMOTION_ENABLED=false')==1;s=s.replace('const val PROMOTION_ENABLED=false','const val PROMOTION_ENABLED=true')
  put(app+name,s)
 core='android/core/src/main/kotlin/co/fallsoft/vipi/core/TranslationIntegrity.kt';s=(R/core).read_text().replace('    fun preservesIdentifiers','    // Private compatibility alias for immutable earlier QA adapters.\n    fun qaLiteralRanges(text:String)=protectedLiteralRanges(text)\n\n    fun preservesIdentifiers');put(core,s)
 name='android/app/src/debug/java/co/fallsoft/vipi/FrameContextAdapter.kt';s=(S/name).read_text();a=s.index('internal data class FrameStarterCandidate');b=s.index('internal class FrameContextAdapter',a);put(name,s[:a]+'internal typealias FrameStarterCandidate = SourceFrameStarterCandidate\n'+s[b:])
 for n in ['SourceFrameProductionTest.kt','SourceFrameProductionDeviceTest.kt']:put('android/app/src/androidTest/java/co/fallsoft/vipi/'+n,(Q/n).read_text())
 put('android/app/src/debug/java/co/fallsoft/vipi/SourceFrameProductionActivity.kt',(Q/'SourceFrameProductionActivity.kt').read_text())
 name='android/app/src/debug/AndroidManifest.xml';s=(S/name).read_text();assert 'SourceFrameProductionActivity' not in s;put(name,s.replace('</application>','<activity android:name=".SourceFrameProductionActivity" android:exported="false" /></application>'))
 put('android/core/src/test/kotlin/co/fallsoft/vipi/core/SourceFrameLiteralRangesTest.kt',(Q/'SourceFrameLiteralRangesTest.kt').read_text())
 for p in sorted((W/'promotion-candidate-r01').glob('source-frames-*.json')):put('android/app/src/debug/assets/immersion/'+p.name,p.read_text())
 out.write_text(json.dumps({'after':after,'delta':delta,'parent_sha256':sha(W/'android-ui-stage-r02.json'),'canonical_promotion':False,'private_promotion':True,'source_frame_assets_debug_only':True},indent=2)+'\n')
if __name__=='__main__':main()
