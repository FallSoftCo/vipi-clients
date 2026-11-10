#!/usr/bin/env python3
from pathlib import Path
import json,hashlib,subprocess,os,shutil,time,signal
W=Path('/home/ai/Development/investigations/vipi-source-context-frames-20261109-r01');S=Path('/home/ai/Development/investigations/vipi-android-source-context-integration-20261109-r01/source')
FLOOR=8*1024**3;PEAK=768*1024**2
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 plan=json.loads((W/'android-stage-r02.json').read_text())
 for p,h in plan['after'].items():assert sha(S/p)==h,p
 out=W/'android-assembly-r02';assert not out.exists();out.mkdir()
 base=shutil.disk_usage(W).free;assert base>=FLOOR+PEAK
 assert int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024>=3*1024**3
 os.sched_setaffinity(0,{2,3})
 gradle='/home/ai/.gradle/wrapper/dists/gradle-8.13-bin/5xuhj0ry160q40clulazy9h7d/gradle-8.13/bin/gradle'
 cmd=[gradle,'--offline','--no-daemon','--max-workers=1','--console=plain','-Dorg.gradle.jvmargs=-Xmx1536m -XX:ActiveProcessorCount=2 -Dfile.encoding=UTF-8','-Pkotlin.compiler.execution.strategy=in-process','-PvipiQaAbi=x86_64','-PvipiSourceContextQualification=true',':core:test','--tests','co.fallsoft.vipi.core.TranslationIntegrityTest','--tests','co.fallsoft.vipi.core.TranslationIntegrityUnicodeTest','--tests','co.fallsoft.vipi.core.TechnicalLiteralIntegrityTest',':app:assembleDebug',':app:assembleDebugAndroidTest']
 receipt={'command':cmd,'script_sha256':sha(Path(__file__)),'stage_sha256':sha(W/'android-stage-r02.json'),'base_free':base,'floor':FLOOR,'additional_peak':PEAK,'basis':'existing APK522825226B + DEX83024896B + Kotlin9502848B + test/metadata/log margin; unchanged native asset inputs reused','success':False}
 (out/'intent.json').write_text(json.dumps(receipt,indent=2)+'\n');start=time.monotonic();proc=None;low=base
 try:
  with (out/'stdout').open('xb') as stdout,(out/'stderr').open('xb') as stderr:
   proc=subprocess.Popen(cmd,cwd=S/'android',stdout=stdout,stderr=stderr,start_new_session=True,env={**os.environ,'ANDROID_HOME':'/home/ai/Android/Sdk'})
   while proc.poll() is None:
    free=shutil.disk_usage(W).free;low=min(low,free);assert free>=FLOOR and base-free<=PEAK,'disk reservation';assert time.monotonic()-start<900,'deadline';time.sleep(1)
   assert proc.returncode==0,proc.returncode
  receipt['artifacts']=[{'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)} for p in (S/'android/app/build/outputs/apk').rglob('*.apk')]
  receipt['core_test_reports']=[{'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)} for p in (S/'android/core/build/test-results/test').glob('TEST-*.xml')]
  receipt['success']=True
 except BaseException as e:receipt['error']=repr(e);raise
 finally:
  if proc and proc.poll() is None:os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=15)
  receipt.update(seconds=time.monotonic()-start,min_free=low,exit=proc.returncode if proc else None);(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
if __name__=='__main__':main()
