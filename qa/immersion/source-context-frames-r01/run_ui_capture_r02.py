#!/usr/bin/env python3
"""Scoped use of retained bounded process/ADB helpers; no dictionary staging."""
from pathlib import Path
import importlib.util,hashlib,json,os,subprocess,time,signal,zipfile,shlex
Q=Path(__file__).resolve().parent;W=Path('/home/ai/Development/investigations/vipi-source-context-frames-20261109-r01')
helper=Q.parent/'android-candidate-producer-r01/launch.py';spec=importlib.util.spec_from_file_location('retained_process_helpers',helper);h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
h.ROOT=W;h.OUT=W/'android-ui-capture-r02';h.FLOOR=8*1024**3
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 assert not h.OUT.exists();h.OUT.mkdir()
 assembly=json.loads((W/'android-ui-assembly-r02/receipt.json').read_text());assert assembly['success']
 plan=json.loads((W/'android-ui-stage-r02.json').read_text())
 for n,digest in plan['after'].items():assert sha(h.SOURCE/n)==digest
 artifacts=assembly['artifacts'];dex=0;payload=0
 for a in artifacts:
  p=Path(a['path']);assert sha(p)==a['sha256'];payload+=p.stat().st_size
  with zipfile.ZipFile(p) as z:dex+=sum(i.file_size for i in z.infolist() if i.filename.endswith('.dex'))
 h.peak=payload+2*dex+h.BOOT_PEAK+64*1024**2+h.OUTPUT;h.base=h.free();h.lowest=h.base;h.stage_started=time.monotonic();h.stage_deadline=1200
 assert h.base>=h.FLOOR+h.peak
 assert int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024>=3*1024**3
 os.sched_setaffinity(0,{2,3});assert h.quick('get-state').returncode!=0
 for proc in Path('/proc').iterdir():
  if not proc.name.isdigit():continue
  try:argv=(proc/'cmdline').read_bytes().split(b'\0')
  except (FileNotFoundError,PermissionError):continue
  assert not (b'-avd' in argv and b'pocket_verify_api35' in argv),'owned AVD already active'
 receipt={'success':False,'script_sha256':sha(Path(__file__)),'helper_sha256':sha(helper),'assembly_sha256':sha(W/'android-ui-assembly-r02/receipt.json'),'free_before':h.base,'additional_reserved':h.peak,'floor':h.FLOOR};h.write(h.OUT/'intent.json',receipt)
 emu=None;flip_prior=None;installed=[];transport_created=False;transport='/data/local/tmp/vipi-frame-route-ui-r02';avd_before=h.allocated(h.AVD);start=time.monotonic()
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
  for name in sorted(p.name for p in (W/'native-inputs-r03').iterdir()):
   remote=transport+'/'+name;local=W/'native-inputs-r03'/name
   h.adb('push-'+name,['push',str(local),remote],60)
   h.shell('stage-mode-'+name,['chmod','644',remote])
   assert h.shell('stage-hash-'+name,['sha256sum',remote]).split()[0]==sha(local)
   h.shell('copy-'+name,['run-as',h.PKG,'cp',remote,'files/'+name])
   assert h.shell('hash-'+name,['run-as',h.PKG,'sha256sum','files/'+name]).split()[0]==sha(local)
  h.shell('transport-remove',['rm','-rf',transport]);transport_created=False
  h.shell('transport-removed',['test','!','-e',transport])
  flip_prior=h.shell('flip-property-before',['getprop','log.tag.VipiFlip']).strip();h.shell('flip-property-enable',['setprop','log.tag.VipiFlip','DEBUG'])
  h.shell('system-anr-before',['logcat','-b','events','-b','system','-b','crash','-d','-t','1000','-s','am_anr:I','ActivityManager:W','AndroidRuntime:E','*:S'],30,False)
  result=h.shell('capture',['am','instrument','-w','-e','class','co.fallsoft.vipi.FrameRouteDeviceTestR02#japaneseFrameRoute,co.fallsoft.vipi.FrameRouteDeviceTestR02#swahiliFrameRoute','-e','vipiDedicatedEmulator','true','-e','vipiFrameRouteUI','true',h.TEST+'/androidx.test.runner.AndroidJUnitRunner'],300)
  h.shell('system-anr-after',['logcat','-b','events','-b','system','-b','crash','-d','-t','1000','-s','am_anr:I','ActivityManager:W','AndroidRuntime:E','*:S'],30,False)
  h.shell('flip-trace',['logcat','-d','-s','VipiFlip:D','*:S'],60,False);h.shell('flip-property-restore',['setprop','log.tag.VipiFlip',flip_prior])
  for language in ['ja','sw']:
   for name in ['proof.json','observations.json','speech-events.json','system-ui-readiness.json','system-dialog-before.png','system-dialog-before.xml','system-dialog-after.png','system-dialog-after.xml','continuous.png','final-state.png','final-hierarchy.xml']+(['native-script.png'] if language=='ja' else []):
    h.guard();target=h.OUT/(language+'-'+name+'.stdout')
    with target.open('xb') as output:
     completed=subprocess.run([h.ADB,'-s','emulator-5620','exec-out','run-as',h.PKG,'cat','files/frame-route-ui-'+language+'/'+name],stdout=output,stderr=subprocess.PIPE,timeout=60)
    h.write(h.OUT/(language+'-'+name+'.json'),{'exit':completed.returncode,'bytes':target.stat().st_size,'sha256':sha(target),'binary_preserved':True})
    assert completed.returncode==0,completed.stderr.decode(errors='replace');h.guard()
  assert 'OK (2 tests)' in result and 'FAILURES!!!' not in result
  for language in ['ja','sw']:
   proof=json.loads((h.OUT/(language+'-proof.json.stdout')).read_text());assert proof['origin']=='SOURCE_REFERENCE_PARTIAL' and proof['translation_calls']==0
   observations=json.loads((h.OUT/(language+'-observations.json.stdout')).read_text());assert any('PLAYING' in x.get('observed_speech_states',[]) for x in observations)
   assert (h.OUT/(language+'-continuous.png.stdout')).read_bytes().startswith(b'\x89PNG')
  receipt.update(success=True,outputs={p.name:sha(p) for p in h.OUT.glob('*.stdout')})
 except BaseException as e:receipt['error']=type(e).__name__+': '+str(e)[:1000];raise
 finally:
  closure={}
  if flip_prior is not None:
   try:closure['flip_property_restored']=h.shell('flip-property-final-restore',['setprop','log.tag.VipiFlip',flip_prior],30,False).strip()
   except BaseException as e:closure['flip_property_restore_error']=repr(e)
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
   if emu.poll() is None:
    h.quick('emu','kill')
    try:emu.wait(30)
    except subprocess.TimeoutExpired:os.killpg(emu.pid,signal.SIGTERM);emu.wait(10)
   closure['owned_emulator_exit']=emu.returncode
  receipt.update(seconds=time.monotonic()-start,min_free=h.lowest,free_after=h.free(),closure=closure,settings_mutation_commands=False);h.write(h.OUT/'receipt.json',receipt)
if __name__=='__main__':main()
