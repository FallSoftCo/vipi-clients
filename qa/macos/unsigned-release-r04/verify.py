import pathlib,json,hashlib,plistlib
n=pathlib.Path('/Users/Apple/Development/vipi-native-delivery-20261109-r01');w=n/'unsigned-release-20261111-r04';a=w/'Vipi.xcarchive';app=a/'Products/Applications/Vipi.app';s=n/'japanese-starter-promotion-r01/source'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
r=json.loads((w/'receipt.json').read_text());assert r['state']=='unsigned_archive_verified'
m=json.loads((n/'apple-release-source-manifest-r04.json').read_text())
for p,v in m['files'].items():assert sha(s/p)==v['sha256'],p
f=json.loads((n/'fixtures.json').read_text())
for p,v in f['assets'].items():assert sha(app/'immersion'/p)==v['sha256'] and (app/'immersion'/p).stat().st_size==v['bytes'],p
notice=app/'immersion/NOTICE.txt';assert sha(notice)=='40b375c220742b2c8b95691cbda864e9d9e7cf1fcdda56e61829bae206fd7e62' and notice.stat().st_size==23931
ni=app/'ThirdPartyNotices/index.json';assert sha(ni)==sha(s/'ios/Vipi/ThirdPartyNotices/index.json');rows=json.loads(ni.read_text())
for row in rows:assert sha(ni.parent/row['file'])==row['sha256']
privacy={str(p.relative_to(app)):{'sha256':sha(p),'contents':plistlib.loads(p.read_bytes())} for p in app.rglob('PrivacyInfo.xcprivacy')}
info=plistlib.loads((app/'Info.plist').read_bytes());assert info['WorkOSClientID']=='client_01M6VYVQQ9GWVNS95DFGABXEW9';assert info['VipiPushEnvironment']=='production'
files={str(p.relative_to(a)):{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(a.rglob('*')) if p.is_file()};mp=w/'artifact-manifest.json';mp.write_text(json.dumps({'source_revision':m['revision'],'files':files},indent=2)+'\n')
report={'state':'PASS exact committed-source unsigned device Release archive','source_revision':m['revision'],'source_manifest_sha256':sha(n/'apple-release-source-manifest-r04.json'),'artifact_manifest_sha256':sha(mp),'compile_inputs_sha256':sha(w/'compile-inputs.json'),'compile_inputs_verified':r['actual_project_compile_inputs_verified'],'source_files_verified':len(m['files']),'artifact_files':len(files),'artifact_bytes':sum(x['bytes'] for x in files.values()),'catalog_assets_verified':len(f['assets']),'notice_entries_verified':len(rows),'notice_sha256':sha(notice),'privacy_manifests':privacy,'public_configuration':{k:info[k] for k in ['CFBundleIdentifier','CFBundleShortVersionString','CFBundleVersion','WorkOSClientID','VipiPushEnvironment']},'signature_present':(app/'_CodeSignature').exists(),'profile_present':(app/'embedded.mobileprovision').exists(),'deployable':False,'normal_startup_qualified':False,'supersedes':['r03 exact 6ceaf4b unsigned archive'],'preserved_experiments_receipt_sha256':sha(n/'preserved-native-experiments-release-r03/receipt.json')}
assert not report['signature_present'] and not report['profile_present']
(w/'closure.json').write_text(json.dumps(report,indent=2)+'\n');print({k:v for k,v in report.items() if k!='privacy_manifests'})
