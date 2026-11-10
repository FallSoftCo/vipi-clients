#!/usr/bin/env python3
from pathlib import Path
import json,hashlib,shutil
Q=Path(__file__).resolve().parent;W=Path('/home/ai/Development/investigations/vipi-source-context-frames-20261109-r01');S=Path('/home/ai/Development/investigations/vipi-android-source-context-integration-20261109-r01/source')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 out=W/'android-ui-stage-r01.json';assert not out.exists()
 freeze=json.loads((W/'android-ui-freeze-r01.json').read_text())
 for name,h in freeze['file_sha256'].items():assert sha(Path(name))==h,name
 parent=json.loads((W/'android-stage-r02.json').read_text());after=parent['after'].copy()
 for name,h in after.items():assert sha(S/name)==h,name
 additions={Q/'FrameRouteQualificationActivity.kt':'android/app/src/debug/java/co/fallsoft/vipi/FrameRouteQualificationActivity.kt',Q/'FrameRouteDeviceTest.kt':'android/app/src/androidTest/java/co/fallsoft/vipi/FrameRouteDeviceTest.kt'}
 for src,name in additions.items():assert not (S/name).exists();shutil.copyfile(src,S/name);after[name]=sha(S/name)
 name='android/app/src/debug/AndroidManifest.xml';backup=W/'android-ui-preparation-r01/prior-AndroidManifest.xml';assert not backup.exists();shutil.copyfile(S/name,backup);shutil.copyfile(W/'android-ui-preparation-r01/AndroidManifest.xml',S/name);after[name]=sha(S/name)
 out.write_text(json.dumps({'after':after,'parent_sha256':sha(W/'android-stage-r02.json'),'test_only_added_paths':list(additions.values()),'private_manifest_before_sha256':sha(backup),'private_manifest_after_sha256':after[name],'input_manifest_sha256':sha(W/'native-inputs-r03/manifest.json'),'canonical_runtime_unchanged':True},indent=2)+'\n')
if __name__=='__main__':main()
