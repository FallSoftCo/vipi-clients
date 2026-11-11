import pathlib,json,hashlib,subprocess,shutil,datetime,re
n=pathlib.Path('/Users/Apple/Development/vipi-native-delivery-20261109-r01');w=n/'unsigned-release-20261111-r04';old=n/'unsigned-release-20261110-r03';a=old/'Vipi.xcarchive'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
c=json.loads((w/'closure.json').read_text());assert c['state'].startswith('PASS') and not c['signature_present'] and not c['profile_present']
app=w/'Vipi.xcarchive/Products/Applications/Vipi.app';pin=app/'immersion/all-pair-source-catalog-001.json';assert sha(pin)=='a0f6f73172cd747a758d677a8c49383fc25591763045a1b0bb77575ba60114a3'
assert c['privacy_manifests']==json.loads((old/'closure.json').read_text())['privacy_manifests']
log=(w/'archive.log').read_text();assert not re.search(r'^CodeSign\s|^\s*/usr/bin/codesign\s',log,re.M)
processes=subprocess.check_output(['ps','-axo','pid,command'],text=True);assert str(a) not in processes
m=json.loads((old/'artifact-manifest.json').read_text());assert a.is_dir() and not a.is_symlink()
for p,v in m['files'].items():assert sha(a/p)==v['sha256'],p
receipt={'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'replacement_closure_sha256':sha(w/'closure.json'),'retired_archive':str(a),'prior_manifest_sha256':sha(old/'artifact-manifest.json'),'prior_files_verified':len(m['files']),'prior_bytes':sum(v['bytes'] for v in m['files'].values()),'catalog_index_sha256':sha(pin),'privacy_manifests_identical':True,'codesign_tasks':0,'active_archive_consumers':False,'retained':['all prior source/receipts/manifests/logs','preserved seven experiments','new r04 archive','shared derived cache and unrelated state'],'state':'verified_retirement_intent'}
p=w/'retirement.json';p.write_text(json.dumps(receipt,indent=2)+'\n');shutil.rmtree(a);receipt['state']='superseded_owned_archive_removed';receipt['free_after']=shutil.disk_usage(n).free;p.write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
