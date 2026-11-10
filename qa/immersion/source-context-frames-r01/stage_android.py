#!/usr/bin/env python3
"""Apply approved test-only overlays to the owned retained Android QA tree, never canonical."""
from pathlib import Path
import json,hashlib,shutil
R=Path(__file__).resolve().parents[3];Q=Path(__file__).resolve().parent;W=Path('/home/ai/Development/investigations/vipi-source-context-frames-20261109-r01');S=Path('/home/ai/Development/investigations/vipi-android-source-context-integration-20261109-r01/source');P=Path('/home/ai/Development/investigations/vipi-starter-content-expansion-20261109-r01/android-stage-final-r04.json');sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 assert not (W/'android-stage-r01.json').exists();parent=json.loads(P.read_text())
 freeze=json.loads((W/'code-review-freeze-r02.json').read_text())
 for path,h in freeze['file_sha256'].items():assert sha(Path(path))==h,path
 for p,h in parent['after'].items():assert sha(S/p)==h,p
 after=parent['after'].copy();deltas={};items=[]
 for lang in ['Japanese','Swahili']:
  for prefix,source in [('', 'android/app/src/main/java/co/fallsoft/vipi/'),('Reference','android/app/src/debug/java/co/fallsoft/vipi/')]:
   fn=prefix+lang+'StarterLookup.kt';items.append((W/'native-overlay-r01/kt'/fn,source+fn))
 items += [(W/'native-literal-overlay-r01/TranslationIntegrity.kt','android/core/src/main/kotlin/co/fallsoft/vipi/core/TranslationIntegrity.kt'),(Q/'FrameContextAdapter.kt','android/app/src/debug/java/co/fallsoft/vipi/FrameContextAdapter.kt'),(Q/'SourceContextFrameTest.kt','android/app/src/androidTest/java/co/fallsoft/vipi/SourceContextFrameTest.kt')]
 for src,name in items:
  dst=S/name;deltas[name]={'before':sha(dst) if dst.exists() else None,'after':sha(src)}
  if dst.exists():backup=W/'prior-android-source'/name;backup.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(dst,backup)
  dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst);after[name]=sha(dst)
 (W/'android-stage-r01.json').write_text(json.dumps({'after':after,'delta':deltas,'parent_sha256':sha(P),'input_manifest_sha256':sha(W/'native-inputs-r02/manifest.json'),'canonical_runtime_unchanged':True},indent=2)+'\n')
if __name__=='__main__':main()
