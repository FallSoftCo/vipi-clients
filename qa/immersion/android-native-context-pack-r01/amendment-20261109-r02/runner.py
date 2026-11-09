#!/usr/bin/env python3
"""Prepared, not run. Each mutation requires an exact root approval bound to this freeze.
No boot logic, downloads, cleanup of other work, Gradle daemon or shared ADB restart.
"""
import argparse,datetime,hashlib,json,os,shutil,signal,subprocess,time,zlib
from pathlib import Path
Q=Path(__file__).resolve().parent
ASSETS=Path('/home/ai/Development/investigations/vipi-android-source-annotations-20261108-r01')
REPO=Path('/home/ai/Development/vipi-production-20261107')
ADB='/home/ai/Android/Sdk/platform-tools/adb'
GRADLE='/home/ai/.gradle/wrapper/dists/gradle-8.13-bin/5xuhj0ry160q40clulazy9h7d/gradle-8.13/bin/gradle'
PKG='co.fallsoft.vipi.contextqa'; COMPONENT=PKG+'/'+PKG+'.ContextProbeInstrumentation'
FLOOR=4*1024**3
PEAK=1900000000 # ceiling includes two decoded copies, build/boot/output; not measured usage
PINS={'d-en.sqlite':(207884288,'5b16dafff9b2a27474792104bad11195ba8aff2236c134cf0265257b92727d68'),
      'd-es.sqlite':(364613632,'fcae976ecf9a8eb79c4ea0e4e214e19894db12c8eb21959270e1b9ce78ab1e8e'),
      'context.sqlite':(4890624,'cd7a8667ff0df53610ef19aa585398e24470716dd23af6d640b7c77dbc3badb4')}
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(1024*1024):h.update(b)
 return h.hexdigest()
def admit():
 free=shutil.disk_usage(Q).free
 if free<FLOOR+PEAK:raise RuntimeError(f'Admission: {free} < floor {FLOOR} + complete peak {PEAK}')
 return free
def checked(p,n,h):
 assert p.is_file() and p.stat().st_size==n and sha(p)==h,str(p)
 assert not any(Path(str(p)+x).exists() for x in ('-wal','-shm','-journal'))
def write(p,x):p.write_text(json.dumps(x,indent=2)+'\n')
def command(cmd,root,name,seconds=120):
 out=root/(name+'.stdout');err=root/(name+'.stderr')
 assert not out.exists(),f'Existing command evidence: {name}'
 begin=time.monotonic();free0=shutil.disk_usage(Q).free;low=free0
 with out.open('wb') as stdout,err.open('wb') as stderr:
  p=subprocess.Popen(cmd,stdout=stdout,stderr=stderr,start_new_session=True,env={**os.environ,'ANDROID_HOME':'/home/ai/Android/Sdk'},cwd=root/'project' if (root/'project').exists() else root)
  try:
   while p.poll() is None:
    free=shutil.disk_usage(Q).free;low=min(low,free)
    if free<FLOOR or time.monotonic()-begin>seconds or out.stat().st_size+err.stat().st_size>16*1024**2:
     raise RuntimeError('Owned command exceeded disk/time/output bound')
    time.sleep(.5)
   assert p.returncode==0,f'{name} exit {p.returncode}'
  finally:
   if p.poll() is None:
    os.killpg(p.pid,signal.SIGTERM)
    try:p.wait(5)
    except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
   write(root/(name+'.receipt.json'),{'cmd':cmd,'exit':p.returncode,'seconds':time.monotonic()-begin,'free_before':free0,'min_free':low,'free_after':shutil.disk_usage(Q).free,'global_disk_delta_not_attributed_to_this_job':True})
 return out.read_text()
def adb(root,name,*args,seconds=120):return command([ADB,'-s','emulator-5620',*args],root,name,seconds)
def main():
 a=argparse.ArgumentParser();a.add_argument('stage',choices=['prepare','build-debug','build-release','probe-debug','probe-release']);a.add_argument('--root',type=Path,required=True);a.add_argument('--approval',type=Path,required=True);a.add_argument('--pack',type=Path);args=a.parse_args()
 freeze=Q/'amendment-freeze.json';binding=json.loads(freeze.read_text())
 for name,h in binding['source_hashes'].items():assert sha(Q/name)==h,name
 approval=json.loads(args.approval.read_text());assert approval['freeze_sha256']==sha(freeze) and args.stage in approval['authorized_stages']
 root=args.root.resolve();assert root.parent==Path('/home/ai/Development/investigations') and root.name.startswith('vipi-android-context-pack-20261109-')
 assert 2 in os.sched_getaffinity(0);os.sched_setaffinity(0,{2})
 free=admit();root.mkdir(exist_ok=True)
 intent=root/(args.stage+'-intent.json');assert not intent.exists(),'One submission per stage/revision; inspect existing receipt before any amendment'
 write(intent,{'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'stage':args.stage,'freeze_sha256':sha(freeze),'free_before':free,'floor':FLOOR,'peak_ceiling':PEAK,'approval_sha256':sha(args.approval)})
 if args.stage=='prepare':
  prepare_start=time.monotonic()
  assert args.pack is not None
  route=json.loads((Q/'asset-route.json').read_text())
  assert args.pack.resolve()==Path(route['pack']['planned_local'])
  checked(args.pack,*PINS['context.sqlite'])
  shutil.copytree(Q,root/'project',ignore=shutil.ignore_patterns('build','.gradle','__pycache__'))
  (root/'project/local.properties').write_text('sdk.dir=/home/ai/Android/Sdk\n')
  assets=root/'project/app/src/main/assets';pins=json.loads((Q/'model-provenance.json').read_text())
  for name,pin in pins.items():
   checked(ASSETS/name,pin['bytes'],pin['sha256'])
   if name.endswith('.bin'):(assets/name).symlink_to(ASSETS/name)
  licenses=assets/'licenses';licenses.mkdir()
  for name in ['tools-LICENSE','tools-NOTICE','models-LICENSE','models-README','slf4j-LICENSE.txt']:shutil.copyfile(ASSETS/name,licenses/name)
  inputs=root/'inputs';inputs.mkdir();shutil.copyfile(args.pack,inputs/'context.sqlite')
  catalog=json.loads((REPO/'data/lexical/catalog.json').read_text())
  # Catalog array nesting is frozen in asset-route.json; only exact paths below.
  route=json.loads((Q/'asset-route.json').read_text())
  for name in ['d-en.sqlite','d-es.sqlite']:
   source=REPO/'data/lexical'/(name+'.zlib');pin=route['compressed'][name]
   checked(source,pin['bytes'],pin['sha256']);decoder=zlib.decompressobj();total=0
   with source.open('rb') as src,(inputs/name).open('xb') as dst:
    while chunk:=src.read(1024*1024):
     while chunk:
      block=decoder.decompress(chunk,1024*1024);chunk=decoder.unconsumed_tail;dst.write(block);total+=len(block)
      assert total<=PINS[name][0] and shutil.disk_usage(Q).free>=FLOOR and time.monotonic()-prepare_start<120
    tail=decoder.flush();dst.write(tail);total+=len(tail)
    assert decoder.eof and not decoder.unused_data and total==PINS[name][0]
   checked(inputs/name,*PINS[name]);os.chmod(inputs/name,0o444)
  write(root/'prepare-receipt.json',{'success':True,'input_bytes':sum(p.stat().st_size for p in inputs.iterdir()),'free_after':shutil.disk_usage(Q).free})
 elif args.stage.startswith('build-'):
  variant=args.stage.split('-')[1].capitalize()
  command(['taskset','-c','2',GRADLE,'--offline','--no-daemon','--max-workers=1','--console=plain',f'-PretainedAssets={ASSETS}',f':app:assemble{variant}'],root,args.stage,240)
  artifact=root/'project/app/build/outputs/apk'/variant.lower()/f'app-{variant.lower()}.apk'
  assert artifact.exists();dest=root/f'{variant.lower()}.apk';shutil.copyfile(artifact,dest)
  proof={'path':str(dest),'bytes':dest.stat().st_size,'sha256':sha(dest)}
  if variant=='Release':
   mapping=root/'project/app/build/outputs/mapping/release/mapping.txt';assert mapping.exists();shutil.copyfile(mapping,root/'release-mapping.txt');proof['mapping_sha256']=sha(mapping)
  write(root/(args.stage+'-artifact.json'),proof)
 else:
  variant=args.stage.split('-')[1];prefix=args.stage
  assert adb(root,prefix+'-boot','shell','getprop','sys.boot_completed').strip()=='1'
  assert adb(root,prefix+'-api','shell','getprop','ro.build.version.sdk').strip()=='35'
  assert adb(root,prefix+'-abi','shell','getprop','ro.product.cpu.abi').strip()=='x86_64'
  avd=adb(root,prefix+'-avd','emu','avd','name');assert avd.splitlines()[0]=='pocket_verify_api35'
  assert not adb(root,prefix+'-prior-package','shell','sh','-c',f'pm path {PKG}; exit 0').strip(),'Preserve an existing package; do not replace it'
  apk=root/f'{variant}.apk';assert apk.exists()
  for name,pin in PINS.items():checked(root/'inputs'/name,*pin)
  installed=False
  try:
   installed=True # Prior package absence was proven; reconcile even uncertain install.
   adb(root,prefix+'-install','install',str(apk))
   prepared=adb(root,prefix+'-prepare','shell','am','instrument','-w','-e','mode','prepare',COMPONENT)
   remote='/storage/emulated/0/Android/data/'+PKG+'/files/context-inputs'
   assert 'CONTEXT_PREPARED:'+remote in prepared
   for name in PINS:adb(root,prefix+'-push-'+name,'push',str(root/'inputs'/name),remote+'/'+name,seconds=180)
   output=adb(root,prefix+'-run','shell','am','instrument','-w','-e','mode','probe',COMPONENT,seconds=180)
   receipts=[json.loads(line.split('CONTEXT_RECEIPT:',1)[1]) for line in output.splitlines() if 'CONTEXT_RECEIPT:' in line]
   assert len(receipts)==1 and receipts[0]['success'], 'Retain exact failure; no retry'
   write(root/(prefix+'-receipt.json'),receipts[0])
  finally:
   if installed:adb(root,prefix+'-uninstall','uninstall',PKG)
   write(root/(prefix+'-closure.json'),{'package_remaining':adb(root,prefix+'-final-package','shell','sh','-c',f'pm path {PKG}; exit 0').strip(),'emulator_left_with_root_owner':True,'settings_changed':False,'main_app_touched':False})
if __name__=='__main__':main()
