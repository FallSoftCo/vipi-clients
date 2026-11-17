import json,os,subprocess,time
from pathlib import Path
q=Path(__file__).parent
floor=4504682496;allowance=150*1024*1024
free=lambda:os.statvfs(q).f_bavail*os.statvfs(q).f_frsize
start=free();assert start>=floor+allowance,(start,floor+allowance)
intent={'device':'emulator-5624','package':'co.fallsoft.vipi.uxqa','floor_bytes':floor,'allowance_bytes':allowance,'initial_free_bytes':start,'started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'class':'co.fallsoft.vipi.ManualTranslationActualDeviceTest','run':'001'}
(q/'actual-intent.json').write_text(json.dumps(intent,indent=2))
command=['adb','-s','emulator-5624','shell','am','instrument','-w','-r','-e','class',intent['class'],'-e','vipiDedicatedEmulator','true','-e','allowModelDownload','true','-e','vipiActualRun','001','co.fallsoft.vipi.uxqa.test/androidx.test.runner.AndroidJUnitRunner']
minimum=start;reason=None
with(q/'actual-instrumentation.log').open('w') as out:
 p=subprocess.Popen(command,stdout=out,stderr=subprocess.STDOUT)
 deadline=time.monotonic()+480
 while p.poll() is None:
  available=free();minimum=min(minimum,available)
  if available<floor:reason='host floor';break
  if start-available>allowance:reason='150MiB additional allocation allowance';break
  if time.monotonic()>deadline:reason='480s runner deadline';break
  time.sleep(.5)
 if reason:
  subprocess.run(['adb','-s','emulator-5624','shell','am','force-stop','co.fallsoft.vipi.uxqa'],timeout=15)
  p.terminate()
 try:code=p.wait(timeout=20)
 except subprocess.TimeoutExpired:p.kill();code=p.wait()
(q/'actual-host-receipt.json').write_text(json.dumps(dict(intent,minimum_free_bytes=minimum,final_free_bytes=free(),max_net_additional_bytes=max(0,start-minimum),stop_reason=reason,adb_exit_code=code,finished_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())),indent=2))
print(json.dumps({'adb_exit_code':code,'stop_reason':reason,'max_net_additional_bytes':max(0,start-minimum)}))
