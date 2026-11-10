#!/usr/bin/env python3
from pathlib import Path
import json,hashlib,shutil,subprocess
R=Path('/home/ai/Development/vipi-production-20261107');Q=Path(__file__).resolve().parent;W=Path('/home/ai/Development/investigations/vipi-conversation-depth-20261109-r01');F=Path('/home/ai/Development/investigations/vipi-source-context-frames-20261109-r01');S=Path('/home/ai/Development/investigations/vipi-android-source-context-integration-20261109-r01/source');sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 out=W/'android-stage-r01.json';assert not out.exists();freeze=json.loads((W/'android-freeze-r01.json').read_text())
 for p,h in freeze['files'].items():assert sha(Path(p))==h,p
 parent=json.loads((F/'android-production-stage-r03.json').read_text());after=parent['after'].copy()
 for p,h in after.items():assert sha(S/p)==h,p
 backup=W/'android-prior-source-r01';backup.mkdir();deltas={}
 paths=['android/app/src/main/java/co/fallsoft/vipi/'+n for n in ['SourceFrameLookup.kt','JapaneseStarterLookup.kt','SwahiliStarterLookup.kt']]+['android/core/src/main/kotlin/co/fallsoft/vipi/core/TranslationIntegrity.kt']
 for name in paths:
  raw=(R/name).read_bytes();assert raw==subprocess.check_output(['git','show','1d42f9c:'+name],cwd=R),name
  text=raw.decode()
  if name.endswith('TranslationIntegrity.kt'):text=text.replace('    fun preservesIdentifiers','    // Private compatibility alias for earlier immutable QA adapters.\n    fun qaLiteralRanges(text:String)=protectedLiteralRanges(text)\n\n    fun preservesIdentifiers')
  dst=S/name;prior=sha(dst);b=backup/name;b.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(dst,b);dst.write_text(text);after[name]=sha(dst);deltas[name]={'before':prior,'after':sha(dst)}
 name='android/app/src/androidTest/java/co/fallsoft/vipi/ConversationDepthTest.kt';assert not (S/name).exists();shutil.copyfile(Q/'ConversationDepthTest.kt',S/name);after[name]=sha(S/name)
 removed=[]
 for p in sorted((R/'data/immersion').glob('source-frames-*.json')):
  name='android/app/src/debug/assets/immersion/'+p.name;dst=S/name;assert sha(dst)==sha(p)
  b=backup/name;b.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(dst,b);removed.append({'path':name,'sha256':sha(dst),'reason':'Exact canonical active main asset now supplies this file; remove private DEBUG duplicate.'});dst.unlink();after.pop(name)
  after['data/immersion/'+p.name]=sha(p)
 out.write_text(json.dumps({'after':after,'delta':deltas,'deleted_debug_duplicates':removed,'parent_sha256':sha(F/'android-production-stage-r03.json'),'canonical_runtime_data_unchanged':True,'base_commit':'1d42f9c09c895a757172c8bdce22f0676c6e0d6f'},indent=2)+'\n')
if __name__=='__main__':main()
