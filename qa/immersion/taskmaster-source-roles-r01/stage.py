from pathlib import Path
import json,hashlib,gzip,base64,subprocess,shlex
w=Path(__file__).parent;q=Path('/home/ai/Development/vipi-production-20261107/qa/immersion/taskmaster-source-roles-r01');sha=lambda b:hashlib.sha256(b).hexdigest()
files={n:(w/n).read_bytes() for n in ['TaskmasterSourceRolesTests.swift','run.py','inputs-200.json']};files['protocol.json']=(q/'protocol.json').read_bytes()
s='''import pathlib,json,sys,gzip,base64,hashlib,subprocess,shutil
r=pathlib.Path('/Users/Apple/Development/vipi-native-delivery-20261109-r01');w=r/'taskmaster-source-roles-r01';assert not w.exists();assert shutil.disk_usage(r).free>16*1024**3
assert subprocess.run(['pgrep','-fl','xcodebuild|swift-frontend|/Vipi.app/Vipi'],capture_output=True).returncode==1
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
plan=json.loads((r/'target-informed-taskmaster-r01/plan-r02.json').read_text())
for p,h in plan['source_hashes'].items():assert sha(r/p)==h,p
payload=json.loads(gzip.decompress(sys.stdin.buffer.read()));w.mkdir()
for n,v in payload.items():
 b=base64.b64decode(v['data']);assert hashlib.sha256(b).hexdigest()==v['sha256'];(w/n).write_bytes(b)
 if n.endswith('Tests.swift'):
  p=r/'source/ios/VipiCryptoTests'/n;assert not p.exists();p.write_bytes(b);plan['source_hashes'][str(p.relative_to(r))]=v['sha256']
for k,args in plan['commands'].items():plan['commands'][k]=[v.replace('target-informed-taskmaster-r01/run-r02','taskmaster-source-roles-r01/run-r01').replace('TaskmasterTargetInformedTests/testFrozenTaskmasterAB','TaskmasterSourceRolesTests/testFrozenSourceRoles') for v in args]
p=json.loads((w/'protocol.json').read_text());plan['bounds']=p['bounds'];plan['scope']=p['scope'];plan['annotation_protocol_sha256']=sha(w/'protocol.json');plan.pop('bindings',None);plan.pop('comparison_sha256',None);plan.pop('amendment',None)
(w/'plan.json').write_text(json.dumps(plan,indent=2)+'\\n');print(json.dumps({'plan_sha256':sha(w/'plan.json'),'protocol_sha256':sha(w/'protocol.json'),'source_hashes':plan['source_hashes'],'free':shutil.disk_usage(r).free}))
'''
payload={n:{'sha256':sha(b),'data':base64.b64encode(b).decode()} for n,b in files.items()}
a=subprocess.run(['ssh','-o','ConnectTimeout=15','apple@macbook-pro','python3 -c '+shlex.quote(s)],input=gzip.compress(json.dumps(payload).encode(),mtime=0),capture_output=True,timeout=60)
(w/'stage.stdout').write_bytes(a.stdout);(w/'stage.stderr').write_bytes(a.stderr);assert a.returncode==0,a.stderr
print(a.stdout.decode())
