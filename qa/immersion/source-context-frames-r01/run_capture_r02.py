#!/usr/bin/env python3
"""Scoped use of retained bounded process/ADB helpers; no dictionary staging."""
from pathlib import Path
import importlib.util,hashlib,json,os,subprocess,time,signal,zipfile,shlex
Q=Path(__file__).resolve().parent;W=Path('/home/ai/Development/investigations/vipi-source-context-frames-20261109-r01')
helper=Q.parent/'android-candidate-producer-r01/launch.py';spec=importlib.util.spec_from_file_location('retained_process_helpers',helper);h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
h.ROOT=W;h.OUT=W/'android-capture-r02';h.FLOOR=8*1024**3;h.OUTPUT=32*1024**2
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 assert not h.OUT.exists();h.OUT.mkdir()
 assembly=json.loads((W/'android-assembly-r02/receipt.json').read_text());assert assembly['success']
 plan=json.loads((W/'android-stage-r02.json').read_text())
 for n,digest in plan['after'].items():assert sha(h.SOURCE/n)==digest
 artifacts=assembly['artifacts'];dex=0;payload=0
 for a in artifacts:
  p=Path(a['path']);assert sha(p)==a['sha256'];payload+=p.stat().st_size
  with zipfile.ZipFile(p) as z:dex+=sum(i.file_size for i in z.infolist() if i.filename.endswith('.dex'))
 h.peak=payload+2*dex+h.BOOT_PEAK+64*1024**2+2*h.OUTPUT;h.base=h.free();h.lowest=h.base;h.stage_started=time.monotonic();h.stage_deadline=1200
 assert h.base>=h.FLOOR+h.peak
 assert int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024>=3*1024**3
 os.sched_setaffinity(0,{2,3});assert h.quick('get-state').returncode!=0
 for proc in Path('/proc').iterdir():
  if not proc.name.isdigit():continue
  try:argv=(proc/'cmdline').read_bytes().split(b'\0')
  except (FileNotFoundError,PermissionError):continue
  assert not (b'-avd' in argv and b'pocket_verify_api35' in argv),'owned AVD already active'
 receipt={'success':False,'script_sha256':sha(Path(__file__)),'helper_sha256':sha(helper),'assembly_sha256':sha(W/'android-assembly-r02/receipt.json'),'free_before':h.base,'additional_reserved':h.peak,'floor':h.FLOOR};h.write(h.OUT/'intent.json',receipt)
 emu=None;installed=[];avd_before=h.allocated(h.AVD);start=time.monotonic()
 try:
  cmd=['taskset','-c','2,3','/home/ai/Android/Sdk/emulator/emulator','-avd','pocket_verify_api35','-port','5620','-no-window','-no-audio','-no-snapshot','-memory','2048','-cores','2','-gpu','swiftshader_indirect']
  with (h.OUT/'emulator.log').open('xb') as log:emu=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  h.write(h.OUT/'owned-emulator.json',{'pid':emu.pid,'cmd':cmd,'startticks':Path(f'/proc/{emu.pid}/stat').read_text().split()[21]})
  boot=time.monotonic()
  while time.monotonic()-boot<300:
   h.guard();assert emu.poll() is None;assert h.allocated(h.AVD)-avd_before<=h.BOOT_PEAK
   r=h.quick('shell','getprop','sys.boot_completed')
   if r.returncode==0 and r.stdout.strip()=='1':break
   time.sleep(2)
  else:raise RuntimeError('boot timeout')
  assert h.quick('emu','avd','name').stdout.splitlines()[0]=='pocket_verify_api35'
  h.shell('main-before',['sh','-c','pm path co.fallsoft.vipi; exit 0'])
  h.shell('settings-before',['settings','list','secure']);h.shell('system-before',['settings','list','system'])
  for a in artifacts:
   pkg=h.TEST if 'androidTest' in a['path'] else h.PKG
   assert not h.shell('prior-'+pkg,['sh','-c',f'pm path {pkg}; exit 0']).strip()
   installed.append(pkg);h.adb('install-'+pkg,['install','--streaming',a['path']],180)
  h.shell('make-files',['run-as',h.PKG,'mkdir','-p','files'])
  for name in sorted(p.name for p in (W/'native-inputs-r03').iterdir()):
   h.command('push-'+name,[h.ADB,'-s','emulator-5620','exec-in',shlex.join(['run-as',h.PKG,'sh','-c','cat > files/'+name])],60,input_path=W/'native-inputs-r03'/name)
   assert h.shell('hash-'+name,['run-as',h.PKG,'sha256sum','files/'+name]).split()[0]==sha(W/'native-inputs-r03'/name)
  result=h.shell('capture',['am','instrument','-w','-e','class','co.fallsoft.vipi.SourceContextFrameRoutingTest','-e','vipiDedicatedEmulator','true','-e','vipiSourceFrames','true',h.TEST+'/androidx.test.runner.AndroidJUnitRunner'],600)
  # Capture a partial result even if an assertion failed.
  h.command('output',[h.ADB,'-s','emulator-5620','exec-out','run-as',h.PKG,'cat','files/frame-output.jsonl'],60)
  h.command('boundary',[h.ADB,'-s','emulator-5620','exec-out','run-as',h.PKG,'cat','files/frame-baseline-parity.json'],60)
  assert 'OK (1 test)' in result and 'FAILURES!!!' not in result
  h.command('status',[h.ADB,'-s','emulator-5620','exec-out','run-as',h.PKG,'cat','files/frame-status.json'],60)
  raw=json.loads((h.OUT/'status.stdout').read_text());assert raw['complete'] and raw['rows']==656 and raw['baseline_comparisons']==1536 and raw['geometry_variants']==780
  assert sum(1 for line in (h.OUT/'output.stdout').open() if line.strip())==656
  h.command('mechanisms',[h.ADB,'-s','emulator-5620','exec-out','run-as',h.PKG,'cat','files/frame-mechanisms.json'],60)
  receipt.update(success=True,output_sha256=sha(h.OUT/'output.stdout'),status_sha256=sha(h.OUT/'status.stdout'),rows=raw['rows'])
 except BaseException as e:receipt['error']=repr(e);raise
 finally:
  closure={}
  if emu is not None:
   for pkg in reversed(installed):
    try:closure[pkg]=h.adb('uninstall-'+pkg,['uninstall',pkg],60,False).strip()
    except BaseException as e:closure[pkg]=repr(e)
   try:
    after=h.shell('main-after',['sh','-c','pm path co.fallsoft.vipi; exit 0'],30,False);closure['main_unchanged']=after==(h.OUT/'main-before.stdout').read_text()
    h.shell('settings-after',['settings','list','secure'],30,False);h.shell('system-after',['settings','list','system'],30,False)
   except BaseException as e:closure['postflight_error']=repr(e)
   if emu.poll() is None:
    h.quick('emu','kill')
    try:emu.wait(30)
    except subprocess.TimeoutExpired:os.killpg(emu.pid,signal.SIGTERM);emu.wait(10)
   closure['owned_emulator_exit']=emu.returncode
  receipt.update(seconds=time.monotonic()-start,min_free=h.lowest,free_after=h.free(),closure=closure,settings_mutation_commands=False);h.write(h.OUT/'receipt.json',receipt)
if __name__=='__main__':main()
