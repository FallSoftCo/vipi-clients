import pathlib,json,hashlib,tarfile,subprocess,time,os,signal,datetime,shutil,plistlib
n=pathlib.Path('/Users/Apple/Development/vipi-native-delivery-20261109-r01');s=n/'japanese-starter-promotion-r01/source';w=n/'unsigned-release-20261111-r04';w.mkdir(exist_ok=False)
r={'started':datetime.datetime.now(datetime.timezone.utc).isoformat(),'revision':'22f6ba0cf0b19e51b5c70448f6a5cab499a0bbcb','state':'preflight','signed':False,'keychain_modified':False,'signing_hold_preserved':True,'floor_bytes':1024**3,'additional_budget':2*1024**3,'stages':[]};r['free_before']=shutil.disk_usage(n).free
assert r['free_before']>r['floor_bytes']+r['additional_budget']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save():(w/'receipt.json').write_text(json.dumps(r,indent=2)+'\n')
def run(name,args,timeout):
 stage={'name':name,'command':args};r['stages'].append(stage);save();start=time.monotonic()
 env={**os.environ,'PATH':'/opt/homebrew/bin:/usr/local/bin:'+os.environ.get('PATH','')}
 with (w/(name+'.log')).open('wb') as f:
  p=subprocess.Popen(args,cwd=s,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True);stage['pid']=p.pid;save()
  while p.poll() is None:
   free=shutil.disk_usage(n).free;r['min_free']=min(r.get('min_free',free),free)
   if free<r['floor_bytes'] or r['free_before']-free>r['additional_budget'] or time.monotonic()-start>timeout:
    os.killpg(p.pid,signal.SIGTERM)
    try:p.wait(timeout=15)
    except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
    raise RuntimeError('bounded unsigned build stopped')
   time.sleep(2)
 stage.update(exit=p.returncode,seconds=time.monotonic()-start);save();assert p.returncode==0,name
try:
 m=json.loads((n/'apple-release-source-manifest-r04.json').read_text())
 for p,v in m['files'].items():assert sha(s/p)==v['sha256'],p
 r['committed_files_verified']=len(m['files']);r['state']='building';save()
 run('prepare',['/bin/zsh',str(s/'scripts/prepare-ios-project.sh')],180)
 ruby="require 'xcodeproj'; require 'json'; p=Xcodeproj::Project.open(ARGV[0]); puts JSON.generate(p.targets.select{|t| ['Vipi','VipiLanguageDetector'].include?(t.name)}.to_h{|t| [t.name,t.source_build_phase.files_references.map{|f|f.real_path.to_s}]})"
 inputs=json.loads(subprocess.check_output(['/opt/homebrew/bin/ruby','-e',ruby,str(s/'ios/Vipi.xcodeproj')],text=True,env={**os.environ,'GEM_HOME':'/opt/homebrew/Cellar/cocoapods/1.17.0_1/libexec'}))
 for target,paths in inputs.items():
  for path in paths:
   rel=str(pathlib.Path(path).resolve().relative_to(s.resolve()));assert rel in m['files'],rel;assert sha(s/rel)==m['files'][rel]['sha256'],rel
 for base in ['ios/Vipi','ios/VipiCore/Sources','ios/VipiLanguageDetector','vendor/cld2']:
  for path in (s/base).rglob('*'):
   if path.is_file() and path.suffix in ['.swift','.cc','.cpp','.c','.h','.m','.mm']:assert str(path.relative_to(s)) in m['files'],str(path)
 (w/'compile-inputs.json').write_text(json.dumps(inputs,indent=2)+'\n');r['actual_project_compile_inputs_verified']={k:len(v) for k,v in inputs.items()};save()

 cmd=['xcodebuild','-workspace',str(s/'ios/Vipi.xcworkspace'),'-scheme','Vipi','-configuration','Release','-sdk','iphoneos','-destination','generic/platform=iOS','-derivedDataPath',str(n/'distribution-archive-r01/DerivedData'),'-clonedSourcePackagesDirPath',str(n/'distribution-archive-r01/SourcePackages'),'-disableAutomaticPackageResolution','-onlyUsePackageVersionsFromResolvedFile','-skipPackageUpdates','-jobs','2','-archivePath',str(w/'Vipi.xcarchive'),'-resultBundlePath',str(w/'archive.xcresult'),'WORKOS_CLIENT_ID=client_01M6VYVQQ9GWVNS95DFGABXEW9','VIPI_PUSH_ENVIRONMENT=production','CODE_SIGNING_ALLOWED=NO','CODE_SIGNING_REQUIRED=NO','CODE_SIGN_IDENTITY=','CODE_SIGN_STYLE=Manual','PROVISIONING_PROFILE_SPECIFIER=','archive']
 run('archive',cmd,900)
 app=w/'Vipi.xcarchive/Products/Applications/Vipi.app';info=plistlib.loads((app/'Info.plist').read_bytes());assert info['CFBundleIdentifier']=='co.fallsoft.vipi' and info['CFBundleShortVersionString']=='1.0' and info['CFBundleVersion']=='1';assert info['WorkOSClientID']=='client_01M6VYVQQ9GWVNS95DFGABXEW9';assert info['VipiPushEnvironment']=='production'
 r.update(state='unsigned_archive_verified',application={'bundle':info['CFBundleIdentifier'],'version':info['CFBundleShortVersionString'],'build':info['CFBundleVersion'],'main_executable_sha256':sha(app/info['CFBundleExecutable']),'privacy_manifests':len(list(app.rglob('PrivacyInfo.xcprivacy'))),'signature_directory_present':(app/'_CodeSignature').exists(),'embedded_profile_present':(app/'embedded.mobileprovision').exists()},must_not_upload=True)
 for p,v in m['files'].items():assert sha(s/p)==v['sha256'],p
except BaseException as e:r.update(state='failed_inspect_before_retry',error=repr(e))
finally:r['free_after']=shutil.disk_usage(n).free;save();print(json.dumps(r),flush=True)
