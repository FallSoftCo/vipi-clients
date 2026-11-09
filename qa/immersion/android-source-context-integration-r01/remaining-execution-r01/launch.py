#!/usr/bin/env python3
"""One approved debug assembly OR one approved bounded lifecycle smoke. No R8.
Prepared source only. No retirement operation is implemented here.
"""
from pathlib import Path
import argparse,datetime,hashlib,json,os,shlex,shutil,signal,subprocess,time,zipfile,re
Q=Path(__file__).resolve().parent
ROOT=Path('/home/ai/Development/investigations/vipi-android-source-context-integration-20261109-r01')
SOURCE=ROOT/'source';OUT=ROOT/'remaining-execution-r01'
ADB='/home/ai/Android/Sdk/platform-tools/adb'
GRADLE='/home/ai/.gradle/wrapper/dists/gradle-8.13-bin/5xuhj0ry160q40clulazy9h7d/gradle-8.13/bin/gradle'
PKG='co.fallsoft.vipi.sourcecontextqa';TEST=PKG+'.test'
AVD=Path('/home/ai/.android/avd/pocket_verify_api35.avd')
FLOOR=4*1024**3;ASSEMBLY_PEAK=3*1024**3;BOOT_PEAK=384*1024**2;OUTPUT=16*1024**2
INPUTS=Path('/home/ai/Development/investigations/vipi-android-context-pack-20261109-r03/inputs')
PINS={'context.sqlite':(4890624,'cd7a8667ff0df53610ef19aa585398e24470716dd23af6d640b7c77dbc3badb4'),'d-en.sqlite':(207884288,'5b16dafff9b2a27474792104bad11195ba8aff2236c134cf0265257b92727d68'),'d-es.sqlite':(364613632,'fcae976ecf9a8eb79c4ea0e4e214e19894db12c8eb21959270e1b9ce78ab1e8e')}
base=0;peak=0;lowest=0;stage_started=0;stage_deadline=0

def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as stream:
  while b:=stream.read(1024*1024):h.update(b)
 return h.hexdigest()
def write(path,value):path.write_text(json.dumps(value,indent=2)+'\n')
def free():return shutil.disk_usage(ROOT).free
def allocated(path):
 seen={}
 for p in path.rglob('*'):
  if p.is_file() and not p.is_symlink():
   s=p.stat();seen[(s.st_dev,s.st_ino)]=s.st_blocks*512
 return sum(seen.values())
def guard():
 global lowest
 now=free();lowest=min(lowest,now)
 assert time.monotonic()-stage_started<stage_deadline,'Overall stage deadline'
 assert now>=FLOOR and base-now<=peak,'Aggregate disk guard; concurrent changes are not attributed to Vipi'
def source_identity():
 authority=json.loads((ROOT/'source-authority.json').read_text())
 for relative,h in authority['source_hashes'].items():assert sha(SOURCE/relative)==h,relative
 for relative,h in authority['data_hashes'].items():assert sha(SOURCE/relative)==h,relative
 return sha(ROOT/'source-authority.json')
def command(name,cmd,deadline,cwd=SOURCE/'android',guarded=True):
 out=OUT/(name+'.stdout');err=OUT/(name+'.stderr');assert not out.exists()
 begin=time.monotonic()
 with out.open('xb') as stdout,err.open('xb') as stderr:
  proc=subprocess.Popen(cmd,cwd=cwd,stdout=stdout,stderr=stderr,start_new_session=True,env={**os.environ,'ANDROID_HOME':'/home/ai/Android/Sdk'})
  try:
   while proc.poll() is None:
    if guarded:guard()
    assert time.monotonic()-begin<deadline,'Owned command deadline'
    assert out.stat().st_size+err.stat().st_size<=OUTPUT,'Output bound'
    time.sleep(.5)
   assert proc.returncode==0,f'{name}: {proc.returncode}'
  finally:
   if proc.poll() is None:
    os.killpg(proc.pid,signal.SIGTERM)
    try:proc.wait(5)
    except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
   write(OUT/(name+'.json'),{'cmd':cmd,'exit':proc.returncode,'seconds':time.monotonic()-begin,'free_after':free()})
 return out.read_text()
def adb(name,args,deadline=30,guarded=True):return command(name,[ADB,'-s','emulator-5620',*args],deadline,guarded=guarded)
def shell(name,args,deadline=30,guarded=True):return adb(name,['shell',shlex.join(args)],deadline,guarded)
def quick(*args):return subprocess.run([ADB,'-s','emulator-5620',*args],capture_output=True,text=True,timeout=8)
def main():
 global base,peak,lowest,stage_started,stage_deadline
 ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['assemble','smoke']);ap.add_argument('--approval',type=Path,required=True);args=ap.parse_args()
 freeze=Q/'execution-freeze.json';cfg=json.loads(freeze.read_text());approval=json.loads(args.approval.read_text())
 assert approval['execution_freeze_sha256']==sha(freeze) and args.stage in approval['authorized_stages']
 assert approval.get('concurrent_reservations_reviewed') is True
 for name,h in cfg['source_hashes'].items():assert sha(Q/name)==h,name
 assert source_identity()==cfg['source_authority_sha256']
 assert json.loads((ROOT/'compile-receipt.json').read_text())['success']
 mem={line.split(':')[0]:int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:')}
 assert mem['MemAvailable']>=3*1024**3,'Keep existing RAM consumers'
 assert {2,3}<=os.sched_getaffinity(0);os.sched_setaffinity(0,{2,3})
 OUT.mkdir(exist_ok=True)
 if args.stage=='assemble':peak=ASSEMBLY_PEAK
 else:
  artifacts=json.loads((OUT/'assembly-artifacts.json').read_text());payload=0;dex=0
  for row in artifacts['apks']:
   p=Path(row['path']);assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256'];payload+=row['bytes']
   with zipfile.ZipFile(p) as z:
    dex+=sum(x.file_size for x in z.infolist() if x.filename.endswith('.dex'))
  # Exact APK payload + exact public inputs + prior boot ceiling + bounded ART/
  # installation metadata allowance derived from actual uncompressed DEX bytes.
  peak=payload+sum(n for n,h in PINS.values())+BOOT_PEAK+2*dex+64*1024**2+OUTPUT
  for name,(size,h) in PINS.items():assert (INPUTS/name).stat().st_size==size and sha(INPUTS/name)==h
 base=free();lowest=base;assert base>=FLOOR+peak
 stage_started=time.monotonic();stage_deadline=1200
 intent=OUT/(args.stage+'-intent.json');assert not intent.exists(),'One submission only; preserve/inspect existing evidence'
 write(intent,{'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'stage':args.stage,'source_authority_sha256':cfg['source_authority_sha256'],'free_before':base,'floor_bytes':FLOOR,'additional_peak_bytes':peak,'approval_sha256':sha(args.approval),'aggregate_disk_delta_not_attribution':True})
 if args.stage=='assemble':
  try:
   cmd=['taskset','-c','2,3',GRADLE,'--offline','--no-daemon','--max-workers=1','--console=plain','-Dorg.gradle.jvmargs=-Xmx1536m -XX:ActiveProcessorCount=2 -Dfile.encoding=UTF-8','-Pkotlin.compiler.execution.strategy=in-process','-PvipiQaAbi=x86_64','-PvipiSourceContextQualification=true',':app:assembleDebug',':app:assembleDebugAndroidTest']
   command('assembly',cmd,900);assert source_identity()==cfg['source_authority_sha256']
   rows=[]
   for path,pkg in [(SOURCE/'android/app/build/outputs/apk/debug/app-debug.apk',PKG),(SOURCE/'android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk',TEST)]:
    assert path.is_file();rows.append({'path':str(path),'bytes':path.stat().st_size,'sha256':sha(path),'expected_package':pkg})
    # Inspect identities/manifest with existing SDK tools, never launch a build.
    badging=command('badging-'+pkg,['/home/ai/Android/Sdk/build-tools/36.0.0/aapt','dump','badging',str(path)],30)
    assert "package: name='"+pkg+"'" in badging
    manifest=command('manifest-'+pkg,['/home/ai/Android/Sdk/build-tools/36.0.0/aapt','dump','xmltree',str(path),'AndroidManifest.xml'],30)
    assert re.search(r'android:extractNativeLibs.*\(type 0x12\)0x0',manifest),'Native extraction would change the install budget'
    command('signature-'+pkg,['/home/ai/Android/Sdk/build-tools/36.0.0/apksigner','verify','--print-certs',str(path)],30)
   write(OUT/'assembly-artifacts.json',{'apks':rows,'copied_apks':False,'build_allocated_bytes':allocated(SOURCE/'android/app/build'),'free_after':free(),'min_free':lowest})
  except BaseException as e:write(OUT/'assembly-failure.json',{'error':repr(e),'free_after':free(),'min_free':lowest});raise
  return
 # Single smoke owns the previously stopped AVD only after exclusive preflight.
 for proc in Path('/proc').iterdir():
  if not proc.name.isdigit():continue
  try:argv=(proc/'cmdline').read_bytes().split(b'\0')
  except (FileNotFoundError,PermissionError):continue
  assert not(b'-avd' in argv and b'pocket_verify_api35' in argv),'Existing AVD owner must be reconciled'
 assert quick('get-state').returncode!=0
 avd_before=allocated(AVD);emu=None;installed=[];started=time.monotonic();receipt={'success':False}
 try:
  cmd=['taskset','-c','2,3','/home/ai/Android/Sdk/emulator/emulator','-avd','pocket_verify_api35','-port','5620','-no-window','-no-audio','-no-snapshot','-memory','2048','-cores','2','-gpu','swiftshader_indirect']
  with (OUT/'emulator.log').open('xb') as log:emu=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  write(OUT/'owned-emulator.json',{'pid':emu.pid,'startticks':Path(f'/proc/{emu.pid}/stat').read_text().split()[21],'cmd':cmd,'avd_allocated_before':avd_before})
  boot=time.monotonic()
  while time.monotonic()-boot<300:
   guard();assert emu.poll() is None;assert allocated(AVD)-avd_before<=BOOT_PEAK
   r=quick('shell','getprop','sys.boot_completed')
   if r.returncode==0 and r.stdout.strip()=='1':break
   time.sleep(2)
  else:raise RuntimeError('Boot deadline exceeded')
  assert quick('shell','getprop','ro.build.version.sdk').stdout.strip()=='35'
  assert quick('shell','getprop','ro.product.cpu.abi').stdout.strip()=='x86_64'
  assert quick('emu','avd','name').stdout.splitlines()[0]=='pocket_verify_api35'
  receipt['boot_seconds']=time.monotonic()-boot
  # Save preflight of the protected main package; never install/clear/uninstall it.
  shell('main-package-before',['sh','-c','pm path co.fallsoft.vipi; exit 0'])
  shell('settings-before',['settings','list','secure']);shell('system-settings-before',['settings','list','system'])
  for row in artifacts['apks']:
   pkg=row['expected_package'];assert not shell('prior-'+pkg,['sh','-c',f'pm path {pkg}; exit 0']).strip()
  for row in artifacts['apks']:
   pkg=row['expected_package'];installed.append(pkg) # Reconcile even uncertain install.
   adb('install-'+pkg,['install','--streaming',row['path']],180)
  # Public source data only; shell creates the isolated app's own external path.
  remote='/storage/emulated/0/Android/data/'+PKG+'/files/source-context-smoke'
  shell('make-input-directory',['mkdir','-p',remote])
  for name in PINS:adb('push-'+name,['push',str(INPUTS/name),remote+'/'+name],180)
  result=shell('lifecycle-smoke',['am','instrument','-w','-e','class','co.fallsoft.vipi.SourceContextLifecycleSmokeTest','-e','sourceContextInputs',remote,TEST+'/androidx.test.runner.AndroidJUnitRunner'],180)
  assert 'OK (1 test)' in result and 'SOURCE_CONTEXT_SMOKE' in result and 'FAILURES!!!' not in result
  receipt['success']=True
 except BaseException as e:receipt['error']=repr(e);raise
 finally:
  closure={'packages':{},'stop':None,'main_package_changed':None}
  if emu is not None:
   # Cleanup commands are independently bounded and exempt from a breached disk
   # guard so that an owned package/process is not abandoned on low storage.
   for pkg in reversed(installed):
    try:closure['packages'][pkg]=adb('uninstall-'+pkg,['uninstall',pkg],60,False).strip()
    except BaseException as e:closure['packages'][pkg]={'error':repr(e)}
   try:
    after=shell('main-package-after',['sh','-c','pm path co.fallsoft.vipi; exit 0'],30,False)
    before=OUT/'main-package-before.stdout'
    closure['main_package_changed']=before.exists() and before.read_text()!=after
    for pkg in installed:closure['packages'][pkg+' remaining']=shell('remaining-'+pkg,['sh','-c',f'pm path {pkg}; exit 0'],30,False).strip()
    shell('settings-after',['settings','list','secure'],30,False);shell('system-settings-after',['settings','list','system'],30,False)
   except BaseException as e:closure['postflight_error']=repr(e)
   try:
    if emu.poll() is None:
     identity=quick('emu','avd','name')
     if identity.returncode==0 and identity.stdout.splitlines()[0]=='pocket_verify_api35':quick('emu','kill')
     try:emu.wait(30)
     except subprocess.TimeoutExpired:
      os.killpg(emu.pid,signal.SIGTERM)
      try:emu.wait(10)
      except subprocess.TimeoutExpired:os.killpg(emu.pid,signal.SIGKILL);emu.wait()
    closure['stop']={'owned_pid':emu.pid,'exit':emu.returncode}
   except BaseException as e:closure['stop']={'error':repr(e)}
  receipt.update({'seconds':time.monotonic()-started,'free_after':free(),'min_free':lowest,'closure':closure,'settings_mutation_commands_issued':False,'source_identity_unchanged':source_identity()==cfg['source_authority_sha256'],'avd_allocated_after':allocated(AVD)})
  write(OUT/'smoke-receipt.json',receipt)
if __name__=='__main__':main()
