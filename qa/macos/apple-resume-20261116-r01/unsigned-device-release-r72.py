import pathlib,json,hashlib,tarfile,subprocess,time,os,signal,datetime,shutil,plistlib
n=pathlib.Path('/Users/Apple/Development/vipi-native-delivery-20261109-r01'); w=n/'unsigned-release-20261116-r72';w.mkdir(); s=w/'source'; m=json.loads((n/'resume-20261116-lookup-r01/manifest-4908.json').read_text());r={'revision':'4908d4e7c9d98d8a33547f52883961108f457547','state':'preflight','signed':False,'must_not_upload':True,'floor_bytes':3*1024**3,'additional_budget':3*1024**3,'free_before':shutil.disk_usage(n).free,'stages':[]}
def save():(w/'receipt.json').write_text(json.dumps(r,indent=2)+'\n')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def verify():
 for p,v in m.items():
  q=s/p
  if not q.is_file() or sha(q)!=v['sha256']:raise RuntimeError('tracked source mismatch '+p)
 for base in ['ios/Vipi','ios/VipiCore/Sources','ios/VipiLanguageDetector','vendor/cld2']:
  for f in (s/base).rglob('*'):
   if f.is_file() and f.suffix in ['.swift','.cc','.cpp','.c','.h','.m','.mm'] and str(f.relative_to(s)) not in m:raise RuntimeError('untracked compile source '+str(f))
def run(name,cmd,timeout):
 stage={'name':name,'command':cmd};r['stages'].append(stage);save();start=time.monotonic()
 with (w/(name+'.log')).open('wb') as log:
  p=subprocess.Popen(cmd,cwd=s,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);stage['pid']=p.pid;save()
  while p.poll() is None:
   free=shutil.disk_usage(n).free;r['min_free']=min(r.get('min_free',free),free)
   if free<r['floor_bytes'] or r['free_before']-free>r['additional_budget'] or time.monotonic()-start>timeout:
    os.killpg(p.pid,signal.SIGTERM)
    try:p.wait(timeout=15)
    except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
    raise RuntimeError('bounded build stopped; inspect before retry')
   time.sleep(2)
 stage.update(exit=p.returncode,seconds=time.monotonic()-start);save()
 if p.returncode:raise RuntimeError(name+' failed')
try:
 assert r['free_before']>r['floor_bytes']+r['additional_budget']
 assert subprocess.run(['pgrep','-x','xcodebuild'],stdout=subprocess.DEVNULL).returncode!=0
 delta=n/'resume-20261116-lookup-r01/release-delta-r72.tar.gz'
 assert sha(delta)=='ee2d4745946863c6eb9b3a418ccf96f0e5835605a2af64a65fbad90ad88af288'
 subprocess.run(['cp','-cR',str(n/'unsigned-simulator-probe-r19/source'),str(s)],check=True)
 with tarfile.open(delta) as t:t.extractall(s,filter='data')
 verify();r['tracked_files_verified']=len(m);r['state']='verified_source';save()
 ruby="require 'xcodeproj'; require 'json'; p=Xcodeproj::Project.open(ARGV[0]); puts JSON.generate(p.targets.select{|t| ['Vipi','VipiLanguageDetector'].include?(t.name)}.to_h{|t| [t.name,t.source_build_phase.files_references.map{|f|f.real_path.to_s}]})"
 env={**os.environ,'GEM_HOME':'/opt/homebrew/Cellar/cocoapods/1.17.0_1/libexec'}
 inputs=json.loads(subprocess.check_output(['/opt/homebrew/bin/ruby','-e',ruby,str(s/'ios/Vipi.xcodeproj')],env=env,text=True))
 for target,paths in inputs.items():
  for path in paths:
   rel=str(pathlib.Path(path).resolve().relative_to(s.resolve()))
   if rel not in m or sha(s/rel)!=m[rel]['sha256']:raise RuntimeError('project source mismatch '+rel)
 (w/'compile-inputs.json').write_text(json.dumps(inputs,indent=2)+'\n');r['compile_inputs']={k:len(v) for k,v in inputs.items()};save()
 cmd=['xcodebuild','-workspace',str(s/'ios/Vipi.xcworkspace'),'-scheme','Vipi','-configuration','Release','-sdk','iphoneos','-destination','generic/platform=iOS','-derivedDataPath',str(n/'distribution-archive-r01/DerivedData'),'-clonedSourcePackagesDirPath',str(n/'distribution-archive-r01/SourcePackages'),'-disableAutomaticPackageResolution','-onlyUsePackageVersionsFromResolvedFile','-skipPackageUpdates','-jobs','2','-archivePath',str(w/'Vipi.xcarchive'),'-resultBundlePath',str(w/'archive.xcresult'),'WORKOS_CLIENT_ID=client_01M6VYVQQ9GWVNS95DFGABXEW9','VIPI_PUSH_ENVIRONMENT=production','CODE_SIGNING_ALLOWED=NO','CODE_SIGNING_REQUIRED=NO','CODE_SIGN_IDENTITY=','CODE_SIGN_STYLE=Manual','PROVISIONING_PROFILE_SPECIFIER=','archive']
 r['state']='building';run('archive',cmd,1200);verify()
 app=w/'Vipi.xcarchive/Products/Applications/Vipi.app'; info=plistlib.loads((app/'Info.plist').read_bytes())
 assert info['CFBundleIdentifier']=='co.fallsoft.vipi' and info['WorkOSClientID']=='client_01M6VYVQQ9GWVNS95DFGABXEW9' and info['VipiPushEnvironment']=='production'
 privacy=sorted(str(p.relative_to(app)) for p in app.rglob('PrivacyInfo.xcprivacy'))
 assert any('MLKit' in p for p in privacy),privacy
 sw=list(app.rglob('sw_dict'));assert len(sw)==1 and sw[0].stat().st_size>0
 assert not (app/'_CodeSignature').exists() and not (app/'embedded.mobileprovision').exists()
 r.update(state='unsigned_archive_verified',bundle=info['CFBundleIdentifier'],version=info['CFBundleShortVersionString'],build=info['CFBundleVersion'],executable_sha256=sha(app/info['CFBundleExecutable']),privacy_manifests=privacy,swahili_resource={'path':str(sw[0].relative_to(app)),'bytes':sw[0].stat().st_size,'sha256':sha(sw[0])})
except BaseException as e:r.update(state='failed_inspect_before_retry',error=repr(e))
finally:r['free_after']=shutil.disk_usage(n).free;save();print(json.dumps(r),flush=True)
