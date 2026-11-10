#!/usr/bin/env python3
"""Scoped use of retained bounded process/ADB helpers; no dictionary staging."""
from pathlib import Path
import importlib.util,hashlib,json,os,subprocess,time,signal,zipfile,shlex
Q=Path(__file__).resolve().parent;W=Path('/home/ai/Development/investigations/vipi-contextual-sense-hold-20261109-r01')
helper=Q.parent/'android-candidate-producer-r01/launch.py';spec=importlib.util.spec_from_file_location('retained_process_helpers',helper);h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
h.ROOT=W;h.OUT=W/'android-control-capture-r02';h.FLOOR=8*1024**3;h.OUTPUT=32*1024**2
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 assert not h.OUT.exists();h.OUT.mkdir()
 assembly=json.loads((W/'android-control-assembly-r02/receipt.json').read_text());assert assembly['success']
 plan=json.loads((W/'android-control-stage-r02.json').read_text())
 for n,digest in plan['after'].items():assert sha(h.SOURCE/n)==digest
 artifacts=assembly['artifacts'];dex=0;payload=0
 for a in artifacts:
  p=Path(a['path']);assert sha(p)==a['sha256'];payload+=p.stat().st_size
  with zipfile.ZipFile(p) as z:dex+=sum(i.file_size for i in z.infolist() if i.filename.endswith('.dex'))
 main=next(Path(a['path'])for a in artifacts if 'androidTest' not in a['path'])
 with zipfile.ZipFile(main) as z:
  for n in ['starter-en-sw-005.json','starter-sw-catalog.json']:
   assert hashlib.sha256(z.read('assets/immersion/'+n)).hexdigest()==sha(W/'candidate-r01'/n)
 h.peak=payload+2*dex+h.BOOT_PEAK+64*1024**2+2*h.OUTPUT;h.base=h.free();h.lowest=h.base;h.stage_started=time.monotonic();h.stage_deadline=1200
 assert h.base>=h.FLOOR+h.peak
 assert int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024>=3*1024**3
 os.sched_setaffinity(0,{2,3});assert h.quick('get-state').returncode!=0
 for proc in Path('/proc').iterdir():
  if not proc.name.isdigit():continue
  try:argv=(proc/'cmdline').read_bytes().split(b'\0')
  except (FileNotFoundError,PermissionError):continue
  assert not (b'-avd' in argv and b'pocket_verify_api35' in argv),'owned AVD already active'
 receipt={'success':False,'script_sha256':sha(Path(__file__)),'helper_sha256':sha(helper),'assembly_sha256':sha(W/'android-control-assembly-r02/receipt.json'),'free_before':h.base,'additional_reserved':h.peak,'floor':h.FLOOR};h.write(h.OUT/'intent.json',receipt)
 emu=None;installed=[];transport_created=False;transport='/data/local/tmp/vipi-contextual-sense-mask-r02';avd_before=h.allocated(h.AVD);start=time.monotonic()
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
  h.shell('transport-absent',['test','!','-e',transport]);h.shell('transport-create',['mkdir',transport]);transport_created=True
  h.shell('transport-mode',['chmod','755',transport])
  for name in sorted(p.name for p in (W/'inputs').iterdir()):
   remote=transport+'/'+name;local=W/'inputs'/name
   h.adb('push-'+name,['push',str(local),remote],60)
   h.shell('stage-mode-'+name,['chmod','644',remote])
   assert h.shell('stage-hash-'+name,['sha256sum',remote]).split()[0]==sha(local)
   h.shell('copy-'+name,['run-as',h.PKG,'cp',remote,'files/'+name])
   assert h.shell('hash-'+name,['run-as',h.PKG,'sha256sum','files/'+name]).split()[0]==sha(local)
  h.shell('transport-remove',['rm','-rf',transport]);transport_created=False
  h.shell('transport-removed',['test','!','-e',transport])
  result=h.shell('capture',['am','instrument','-w','-e','class','co.fallsoft.vipi.ContextualSenseMaskTest','-e','vipiDedicatedEmulator','true','-e','vipiContextualSenseMask','true',h.TEST+'/androidx.test.runner.AndroidJUnitRunner'],600)
  h.command('status',[h.ADB,'-s','emulator-5620','exec-out','run-as',h.PKG,'cat','files/android-status.json'],60)
  h.command('controls',[h.ADB,'-s','emulator-5620','exec-out','run-as',h.PKG,'cat','files/android-controls.json'],60)
  assert 'OK (1 test)'  in result and 'FAILURES!!!' not in result
  raw=json.loads((h.OUT/'status.stdout').read_text());assert raw['rows']==0 and raw['control_cases']==4 and not raw['default_capture_replayed'] and raw['translation_calls']==0
  controls=json.loads((h.OUT/'controls.stdout').read_text());assert controls['unmasked_legacy_spans']==1 and controls['masked_legacy_spans']==0
  receipt.update(success=True,controls_sha256=sha(h.OUT/'controls.stdout'),status_sha256=sha(h.OUT/'status.stdout'),qualification=raw)
 except BaseException as e:receipt['error']=repr(e);raise
 finally:
  closure={}
  if emu is not None:
   if transport_created:
    try:
     h.shell('transport-cleanup',['rm','-rf',transport],30,False);closure['owned_transport_removed']=h.shell('transport-cleanup-check',['sh','-c','test ! -e '+shlex.quote(transport)+' && echo removed'],30,False).strip()=='removed'
    except BaseException as e:closure['transport_cleanup_error']=repr(e)
   for pkg in reversed(installed):
    try:closure[pkg]=h.adb('uninstall-'+pkg,['uninstall',pkg],60,False).strip()
    except BaseException as e:closure[pkg]=repr(e)
   try:
    after=h.shell('main-after',['sh','-c','pm path co.fallsoft.vipi; exit 0'],30,False);closure['main_unchanged']=after==(h.OUT/'main-before.stdout').read_text()
    h.shell('settings-after',['settings','list','secure'],30,False);h.shell('system-after',['settings','list','system'],30,False)
   except BaseException as e:closure['postflight_error']=repr(e)
   closure['exit_before_requested_shutdown']=emu.poll()
   if emu.poll() is None:
    stopped=h.quick('emu','kill');closure['quit_command_exit']=stopped.returncode
    try:emu.wait(30)
    except subprocess.TimeoutExpired:os.killpg(emu.pid,signal.SIGTERM);emu.wait(10)
   closure['owned_emulator_exit']=emu.returncode
  receipt.update(seconds=time.monotonic()-start,min_free=h.lowest,free_after=h.free(),closure=closure,settings_mutation_commands=False);h.write(h.OUT/'receipt.json',receipt)
if __name__=='__main__':main()
