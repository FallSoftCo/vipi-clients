"""Root-owned, temporary local fixture; existing nobody identity, no services."""
import pathlib,json,hashlib,runpy,shutil,os,sys
sys.dont_write_bytecode=True
root=pathlib.Path('/var/tmp/vipi-upgrade-access-r01');assert os.geteuid()==0 and not root.exists();root.mkdir(mode=0o755)
helper=runpy.run_path('/home/ai/Development/vipi-production-20261107/ops/upgrade-service.py');rev='a'*40
checks=[]
def manifest():
 files={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file() and p.name!='manifest.json'}
 (root/'manifest.json').write_text(json.dumps({'revision':rev,'files':files}));(root/'manifest.json').chmod(0o644)
def deny(label):
 helper['verify_release'](root,rev)
 try:helper['verify_service_access'](root,service_user='nobody')
 except RuntimeError as e:assert str(e)=='Candidate service-user access/import preflight failed';checks.append(label)
 else:raise AssertionError(label)
try:
 p=root/'deps/vipi';p.mkdir(parents=True);(root/'deps').chmod(0o755);p.chmod(0o755)
 for name,data in [('__init__.py',''),('config.py','MARKER = "fixture"\n'),('api.py','from .config import MARKER\nassert MARKER == "fixture"\n')]:
  (p/name).write_text(data);(p/name).chmod(0o644)
 manifest();root.chmod(0o700);deny('0700 candidate passes root hash verifier but fails unprivileged cwd before activation')
 root.chmod(0o755);p.chmod(0o700);deny('0700 nested package directory denied')
 p.chmod(0o755);(p/'config.py').chmod(0o600);deny('unreadable manifest member denied despite valid root hash')
 (p/'config.py').chmod(0o644);helper['verify_service_access'](root,service_user='nobody');checks.append('accessible candidate imports exact local modules')
 (p/'api.py').write_text('raise RuntimeError("synthetic broken import")\n');manifest();deny('readable/hash-valid candidate with broken import denied')
 assert not list(root.rglob('__pycache__'));checks.append('bytecode writes disabled')
 print(json.dumps({'passed':True,'checks':checks,'real_os_identity':'nobody','service_restart':False,'network_or_database_calls':False}))
finally:shutil.rmtree(root)
