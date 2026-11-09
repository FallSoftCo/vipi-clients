import pathlib,json,subprocess,hashlib,shutil,datetime,time,os,signal,plistlib,base64
root=pathlib.Path('/Users/Apple/Development/vipi-native-delivery-20261109-r01');work=root/'starter-content-expansion-r01/run-r02';work.mkdir(exist_ok=False)
plan=json.loads((root/'starter-content-expansion-r01/plan-r02.json').read_text());src=root/'japanese-starter-promotion-r01/source';device='46CB569D-EA59-40E3-82CC-F4A0F36EDB87'
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def call(c):return subprocess.check_output(c,text=True,timeout=30).strip()
def size():
 paths=[root/'app-build-r01',root/'native-context-pack-r01',root/'native-candidate-producer-r01',root/'native-candidate-binding-r01',root/'contextual-fallback-r01',root/'japanese-starter-promotion-r01',root/'swahili-starter-promotion-r01',src/'ios',root/'starter-packing-density-r01',root/'starter-content-expansion-r01']
 current=subprocess.run(['xcrun','simctl','get_app_container',device,'co.fallsoft.vipi','data'],capture_output=True,text=True,timeout=15)
 if current.returncode==0:
  cache=pathlib.Path(current.stdout.strip())/'Library/Caches/lexical-public'
  if cache.exists():paths.append(cache)
 return sum(int(call(['du','-sk',str(p)]).split()[0])*1024 for p in paths)
receipt={'complete':False,'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'plan_sha256':sha(root/'starter-content-expansion-r01/plan-r02.json'),'stages':[],'scope':plan['scope']}
def save(): (work/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
def stage(name,cmd,deadline):
 s={'name':name,'command':cmd,'deadline_seconds':deadline};receipt['stages'].append(s);save();start=time.monotonic()
 with (work/(name+'.log')).open('wb') as log:
  proc=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,env={**os.environ,'PATH':'/opt/homebrew/bin:/usr/local/bin:'+os.environ.get('PATH','')});s['pid']=proc.pid;save()
  try:
   while proc.poll() is None:
    used=size();s['peak_owned_bytes']=max(s.get('peak_owned_bytes',0),used)
    if used-receipt['initial_owned_bytes']>8*1024**3:raise RuntimeError('owned additional exceeds8GiB')
    if shutil.disk_usage(root).free<8*1024**3:raise RuntimeError('physical free below8GiB')
    if time.monotonic()-start>deadline:raise TimeoutError(name)
    time.sleep(2)
  except BaseException:
   os.killpg(proc.pid,signal.SIGTERM)
   try:proc.wait(timeout=10)
   except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
   raise
 s.update(exit_code=proc.returncode,seconds=time.monotonic()-start,log_sha256=sha(work/(name+'.log')));save()
 if proc.returncode:raise RuntimeError(name+' failed; no replay')
state_saved=False;test_started=False
try:
 receipt['initial_owned_bytes']=size();receipt['free_before']=shutil.disk_usage(root).free
 assert receipt['free_before']>16*1024**3
 running=subprocess.run(['pgrep','-fl','xcodebuild|swift-frontend'],capture_output=True,text=True);assert running.returncode==1,running.stdout
 receipt['labs']={str(pid):call(['ps','-p',str(pid),'-o','command=']) for pid in [55552,65698]}
 for name,h in plan['source_hashes'].items():assert sha(root/name)==h,name
 assert sha(root/'native-context-pack-r01/inputs/rule-fixtures.json')=='1a3203d294f4d2fd9f3d00fd7dfa08e04bdbecda905967d3c80d5c7c20cac0ef'
 receipt['synthetic_fixture_sha256']='1a3203d294f4d2fd9f3d00fd7dfa08e04bdbecda905967d3c80d5c7c20cac0ef'
 expected={x['path']:x['sha256'] for x in json.loads((root/'source-authority.json').read_text())['files']};expected.update({k:v['sha256'] for k,v in json.loads((root/'app-inputs-r01.json').read_text())['files'].items()});expected.update(json.loads((root/'incremental-build-r03/receipt.json').read_text())['overlays'])
 expected.update({p.removeprefix('japanese-starter-promotion-r01/source/'):h for p,h in plan['source_hashes'].items() if p.startswith('japanese-starter-promotion-r01/source/')})
 for name,h in {'ios/Vipi/EnglishSourceRoleProvider.swift':'e96d502ff83dfd5bd20bc6c7833673d83a88f72ed46e97552e7ec6087b7557a1','ios/VipiCryptoTests/EnglishSourceRoleProviderTests.swift':'ddf9d6b9f2df3b922f89e58042f8ab1a347fc01285f6dc7d2b08908a50a251e9','ios/VipiCryptoTests/EnglishSourceRoleFixture.swift':'8c8afa26ae80454ee363caebad691d2a570ea0487e446f481c13380dd2a323ff'}.items():expected[name]=h
 diffs=[p for p,h in expected.items() if sha(src/p)!=h];receipt['source_files_verified']=len(expected);receipt['source_differences']=diffs;save();assert not diffs,diffs
 pins=json.loads((src/'ios/Package.resolved').read_text())['pins'];receipt['pins']=[]
 for pin in pins:
  checkout=root/'app-build-r01/SourcePackages/checkouts'/pin['identity'];head=call(['git','-C',str(checkout),'rev-parse','HEAD']);dirty=call(['git','-C',str(checkout),'status','--porcelain','--untracked-files=no']);assert head==pin['state']['revision'] and not dirty;receipt['pins'].append({'identity':pin['identity'],'revision':head,'tracked_clean':True})
 apps=subprocess.run(['pgrep','-fl','/Vipi.app/Vipi'],capture_output=True,text=True);assert apps.returncode==1,apps.stdout
 container=pathlib.Path(call(['xcrun','simctl','get_app_container',device,'co.fallsoft.vipi','data']));prefs=container/'Library/Preferences/co.fallsoft.vipi.plist';before=plistlib.loads(prefs.read_bytes());(work/'before-preferences.plist').write_bytes(prefs.read_bytes());receipt['before_container']=str(container);receipt['before_preferences_sha256']=sha(prefs);state_saved=True;save()
 stage('prepare',plan['commands']['prepare'],180)
 assert sha(src/'ios/Package.resolved')==expected['ios/Package.resolved'];assert sha(src/'ios/Podfile.lock')==expected['ios/Podfile.lock']
 stage('core-test',plan['commands']['core-test'],600)
 stage('build',plan['commands']['build'],900)
 products=root/'app-build-r01/Build/Products';runs=list(products.glob('VipiSimulator_iphonesimulator*-arm64.xctestrun'));assert len(runs)==1,[str(p) for p in runs]
 original=plistlib.loads(runs[0].read_bytes())
 def replace(v):
  if isinstance(v,str):return v.replace('__TESTROOT__',str(products))
  if isinstance(v,list):return [replace(x) for x in v]
  if isinstance(v,dict):return {k:replace(x) for k,x in v.items()}
  return v
 x=replace(original);assert 'VipiCryptoTests' in x;x['VipiCryptoTests']['CommandLineArguments']=['-vipi-full-reading-qa'];x['VipiCryptoTests'].setdefault('EnvironmentVariables',{})['VIPI_CONTENT_EXPANSION_QA']=str(root/'starter-content-expansion-r01/inputs-r03');(work/'qualification.xctestrun').write_bytes(plistlib.dumps(x))
 receipt['built_hashes']={str(p):sha(p) for p in [runs[0],work/'qualification.xctestrun',products/'Simulator-iphonesimulator/Vipi.app/Vipi',products/'Simulator-iphonesimulator/Vipi.app/PlugIns/VipiCryptoTests.xctest/VipiCryptoTests']};save()
 test_started=True;stage('test',plan['commands']['test'],600);receipt['complete']=True
except BaseException as exc:receipt['error']=repr(exc)
finally:
 if state_saved and test_started:
  try:
   subprocess.run(['xcrun','simctl','terminate',device,'co.fallsoft.vipi'],capture_output=True,timeout=30)
   container=pathlib.Path(call(['xcrun','simctl','get_app_container',device,'co.fallsoft.vipi','data']));prefs=container/'Library/Preferences/co.fallsoft.vipi.plist';after=plistlib.loads(prefs.read_bytes());merged=dict(after);merged.update(before)
   if 'vipi-private-speech-generation' in after:merged['vipi-private-speech-generation']=after['vipi-private-speech-generation']
   restore=work/'restored-preferences.plist';restore.write_bytes(plistlib.dumps(merged));subprocess.run(['xcrun','simctl','spawn',device,'defaults','import','co.fallsoft.vipi',str(restore)],check=True,capture_output=True,timeout=30)
   verified=plistlib.loads(subprocess.check_output(['xcrun','simctl','spawn',device,'defaults','export','co.fallsoft.vipi','-'],timeout=30));assert all(verified[k]==v for k,v in before.items() if k!='vipi-private-speech-generation');assert verified.get('vipi-private-speech-generation')==merged.get('vipi-private-speech-generation')
   assert subprocess.run(['pgrep','-fl','/Vipi.app/Vipi'],capture_output=True).returncode==1
   receipt['state_closure']={'restored':True,'original_keys_verified':list(before),'current_extra_keys_preserved':[k for k in after if k not in before],'app_not_running':True,'data_preserved':True,'container':str(container),'labs_alive':all(subprocess.run(['kill','-0',str(pid)],capture_output=True).returncode==0 for pid in [55552,65698])}
  except BaseException as exc:receipt['state_closure']={'restored':False,'error':repr(exc)};receipt['complete']=False
 receipt['free_after']=shutil.disk_usage(root).free;receipt['final_owned_bytes']=size();save();print(json.dumps(receipt),flush=True)
