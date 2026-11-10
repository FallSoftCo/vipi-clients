#!/usr/bin/env python3
from pathlib import Path
import json,hashlib,shutil
Q=Path(__file__).resolve().parent;W=Path('/home/ai/Development/investigations/vipi-source-context-frames-20261109-r01');S=Path('/home/ai/Development/investigations/vipi-android-source-context-integration-20261109-r01/source')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 out=W/'android-stage-r02.json';assert not out.exists()
 freeze=json.loads((W/'routing-amendment-freeze-r01.json').read_text())
 for name,h in freeze['file_sha256'].items():assert sha(Path(name))==h,name
 parent=json.loads((W/'android-stage-r01.json').read_text());after=parent['after'].copy()
 for name,h in after.items():assert sha(S/name)==h,name
 name='android/app/src/androidTest/java/co/fallsoft/vipi/SourceContextFrameRoutingTest.kt';target=S/name;assert not target.exists();shutil.copyfile(Q/'SourceContextFrameRoutingTest.kt',target);after[name]=sha(target)
 out.write_text(json.dumps({'after':after,'parent_sha256':sha(W/'android-stage-r01.json'),'new_test_only_path':name,'new_test_sha256':sha(target),'input_manifest_sha256':sha(W/'native-inputs-r03/manifest.json'),'canonical_runtime_unchanged':True},indent=2)+'\n')
if __name__=='__main__':main()
