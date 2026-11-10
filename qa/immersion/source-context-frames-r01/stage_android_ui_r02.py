#!/usr/bin/env python3
from pathlib import Path
import json,hashlib,shutil
Q=Path(__file__).resolve().parent;W=Path('/home/ai/Development/investigations/vipi-source-context-frames-20261109-r01');S=Path('/home/ai/Development/investigations/vipi-android-source-context-integration-20261109-r01/source');sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 out=W/'android-ui-stage-r02.json';assert not out.exists();freeze=json.loads((W/'android-ui-amendment-r02.json').read_text())
 for name,h in freeze['file_sha256'].items():assert sha(Path(name))==h,name
 parent=json.loads((W/'android-ui-stage-r01.json').read_text());after=parent['after'].copy()
 for n,h in after.items():assert sha(S/n)==h,n
 name='android/app/src/androidTest/java/co/fallsoft/vipi/FrameRouteDeviceTestR02.kt';assert not (S/name).exists();shutil.copyfile(Q/'FrameRouteDeviceTestR02.kt',S/name);after[name]=sha(S/name)
 out.write_text(json.dumps({'after':after,'parent_sha256':sha(W/'android-ui-stage-r01.json'),'new_test_only_path':name,'canonical_runtime_unchanged':True},indent=2)+'\n')
if __name__=='__main__':main()
