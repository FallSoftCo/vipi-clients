#!/usr/bin/env python3
from pathlib import Path
import json,hashlib,shutil
R=Path('/home/ai/Development/vipi-production-20261107');Q=Path(__file__).resolve().parent;W=Path('/home/ai/Development/investigations/vipi-contextual-sense-hold-20261109-r01');P=Path('/home/ai/Development/investigations/vipi-conversation-depth-20261109-r01');S=Path('/home/ai/Development/investigations/vipi-android-source-context-integration-20261109-r01/source')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 out=W/'android-stage-r01.json';assert not out.exists()
 for p,h in json.loads((W/'android-freeze-r01.json').read_text())['files'].items():assert sha(Path(p))==h,p
 after=json.loads((P/'android-stage-r01.json').read_text())['after'].copy()
 for p,h in after.items():assert sha(S/p)==h,p
 backup=W/'android-prior-source-r01';backup.mkdir();delta={}
 paths={'android/app/src/main/java/co/fallsoft/vipi/SwahiliStarterLookup.kt':R/'android/app/src/main/java/co/fallsoft/vipi/SwahiliStarterLookup.kt','android/app/src/androidTest/java/co/fallsoft/vipi/ContextualSenseHoldTest.kt':Q/'ContextualSenseHoldTest.kt'}
 for name in ['starter-en-sw-005.json','starter-sw-catalog.json']:paths['android/app/src/debug/assets/immersion/'+name]=W/'candidate-r01'/name
 for name,src in paths.items():
  dst=S/name;prior=sha(dst)if dst.exists()else None
  if dst.exists():b=backup/name;b.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(dst,b)
  dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst);after[name]=sha(dst);delta[name]={'before':prior,'after':sha(dst)}
 out.write_text(json.dumps({'after':after,'delta':delta,'parent_sha256':sha(P/'android-stage-r01.json'),'canonical_data_unchanged':True,'private_debug_candidate_assets':True},indent=2)+'\n')
if __name__=='__main__':main()
