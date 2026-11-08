from pathlib import Path
import subprocess,os,time,json,signal,shutil
p=Path('/home/ai/Development/investigations/vipi-android-opennlp-runtime-20261108-r01');avd=Path('/home/ai/.android/avd/pocket_verify_api35.avd')
def allocated(root):return sum(f.stat().st_blocks*512 for f in root.rglob('*') if f.is_file())
assert not any('pocket_verify_api35' in Path('/proc',s,'cmdline').read_bytes().decode(errors='ignore') for s in os.listdir('/proc') if s.isdigit() and s!=str(os.getpid()) and Path('/proc',s,'cmdline').exists())
assert subprocess.run(['adb','-s','emulator-5620','get-state'],capture_output=True).returncode!=0
base=allocated(avd);free=shutil.disk_usage(p).free;assert free>8589934592+402653184
cmd=['taskset','-c',str(min(os.sched_getaffinity(0))),'/home/ai/Android/Sdk/emulator/emulator','-avd','pocket_verify_api35','-port','5620','-no-window','-no-audio','-no-snapshot','-memory','2048','-cores','1','-gpu','swiftshader_indirect']
x={'before_allocated_bytes':base,'free_before':free,'cmd':cmd,'booted':False,'steps':[]};(p/'boot-intent-r02.json').write_text(json.dumps(x,indent=2)+'\n')
with (p/'emulator-r02.log').open('w') as log:proc=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
x['pid']=proc.pid;x['sid']=os.getsid(proc.pid);start=time.monotonic()
try:
 while time.monotonic()-start<180:
  growth=allocated(avd)-base;free=shutil.disk_usage(p).free;x['peak_avd_growth_bytes']=max(x.get('peak_avd_growth_bytes',0),growth);x['free_after']=free
  if growth>134217728 or free<8589934592+268435456:raise RuntimeError('startup disk admission breached')
  if proc.poll() is not None:raise RuntimeError('emulator exited '+str(proc.returncode))
  r=subprocess.run(['adb','-s','emulator-5620','shell','getprop','sys.boot_completed'],capture_output=True,text=True,timeout=5)
  if r.returncode==0 and r.stdout.strip()=='1':x['booted']=True;break
  time.sleep(2)
 if not x['booted']:raise RuntimeError('boot deadline')
 x['device']=subprocess.check_output(['adb','-s','emulator-5620','shell','getprop','ro.build.version.sdk'],text=True).strip();assert x['device']=='35'
except Exception as e:
 x['error']=repr(e)
 if proc.poll() is None:os.killpg(proc.pid,signal.SIGTERM)
finally:
 x['elapsed_seconds']=time.monotonic()-start;(p/'boot-receipt-r02.json').write_text(json.dumps(x,indent=2)+'\n');print(json.dumps(x,indent=2))
