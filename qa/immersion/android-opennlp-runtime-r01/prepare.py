from pathlib import Path
import json,hashlib,os,shutil,datetime
q=Path(__file__).resolve().parent;root=q.parents[2];p=Path('/home/ai/Development/investigations/vipi-android-opennlp-runtime-20261108-r01');p.mkdir(mode=0o700,exist_ok=False)
sha=lambda b:hashlib.sha256(b).hexdigest();inputpath=root/'qa/immersion/native-source-annotations-r01/inputs.json';b=inputpath.read_bytes();assert sha(b)=='cb37306db9723bf39ea41204674515c890fa12186d7e6ac052db06e6d1f27b14'
cases=[{'id':x['id'],'text':x['text']} for x in json.loads(b)['cases']];assert len(cases)==116
review=Path('/home/ai/Development/investigations/vipi-source-role-veto-20261108-r01/android-review-source-only-inputs-r01.json').read_bytes();assert sha(review)=='8644ec214a61c2c23f5e3a020cf1325507468e555713caf3d57b8692d6fbf7c7';cases += [{'id':x['id'],'text':x['text']} for x in json.loads(review)['cases']];assert len(cases)==148
for f in q.rglob('*'):
 if f.is_file(): dest=p/'project'/f.relative_to(q);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(f,dest)
a=p/'project/app/src/main/assets';a.mkdir(parents=True);(a/'inputs.json').write_text(json.dumps({'cases':cases},ensure_ascii=False,separators=(',',':'))+'\n')
m=Path('/home/ai/Development/investigations/vipi-android-source-annotations-20261108-r01');pins=json.loads((root/'qa/immersion/source-role-veto-r01/android-freeze.json').read_text())['verified_assets']
for n,h in pins.items():assert sha((m/n).read_bytes())==h
for n in pins:
 if n.endswith('.bin'):(a/n).symlink_to(m/n)
lic=a/'licenses';lic.mkdir()
for name in ['tools-LICENSE','tools-NOTICE','models-LICENSE','models-README','slf4j-LICENSE.txt']:shutil.copyfile(m/name,lic/name)
(p/'project/local.properties').write_text('sdk.dir=/home/ai/Android/Sdk\n')
assert shutil.disk_usage(p).free>8589934592+402653184
plan={'schema':'vipi.android-opennlp-runtime-plan.r01','frozen_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'before_build_or_runtime':True,'inputs_source_sha256':sha(b),'id_text_only_sha256':sha((a/'inputs.json').read_bytes()),'cases':148,'review32_input_sha256':sha(review),'assets':pins,'source_hashes':{str(f.relative_to(q)):sha(f.read_bytes()) for f in q.rglob('*') if f.is_file()},'scope':'Isolated Java Android QA package co.fallsoft.vipi.opennlpqa; debug then R8 optimized debug-signed qualification build; no production dependency/catalog change','runtime':'Reuse existing pocket_verify_api35 AVD on5620; no new AVD/disk/snapshot. Existing5584 untouched.','limits':{'combined_additional_bytes':402653184,'build_growth_ceiling_bytes':268435456,'emulator_growth_ceiling_bytes':134217728,'free_floor_bytes':8589934592,'build_workers':1,'build_jvm_heap_mib':384,'emulator_cores':1,'emulator_requested_ram_mib':2048,'boot_seconds':180,'each_build_seconds':240,'each_runtime_seconds':120},'admission_basis':'Retained small isolated harness app/build21.4MiB +.gradle0.6MiB.256MiB build and128MiB emulator startup are enforced ceilings, not claimed measured peak.38GiB hostRAM available.','network':'Offline Gradle; no INTERNET permission in QA package; model assets bundled, no model downloads; no shared network settings changed.','measurements':['exactUTF16/rawtags/rawscores vs same116 JVMreference','threepassesrepeat','model-load/per-pass timings','ownprocessVmHWM/VmRSS/PSS,Javaheapused/committed/max,nativeheap'],'coverage_limits':['API35 x86_64 only','API28 andARM64 not qualified','No lexicalsense or genericNERapproval'],'execution_state':'prepared'}
(q/'plan.json').write_text(json.dumps(plan,indent=2)+'\n');(p/'plan.json').write_text(json.dumps(plan,indent=2)+'\n');print(str(p))
