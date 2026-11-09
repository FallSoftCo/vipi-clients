import hashlib,json,os,posixpath,shutil,socket,subprocess
from pathlib import Path
r=Path('/srv/fallsoft/staging/vipi-apertium-occurrence-roles-20261109-r01');assert socket.gethostname()=='fallsoft-production-20261106';m=json.loads((r/'retained-runtime-manifest.json').read_text());expanded=[]
def resolved(name):
 v=m['files'][name]
 return resolved(posixpath.normpath(str(Path(name).parent/v['symlink']))) if 'symlink' in v else v['sha256']
for name,v in m['files'].items():
 assert hashlib.sha256((r/name).read_bytes()).hexdigest()==resolved(name),name
 if 'symlink' in v:expanded.append(name)
E=os.environ.copy();E['LD_LIBRARY_PATH']=str(r/'root/usr/lib/x86_64-linux-gnu');checks={}
for name in ['apertium-destxt','lt-proc','apertium-tagger']:
 p=r/'root/usr/bin'/name;x=subprocess.run(['ldd',str(p)],capture_output=True,text=True,env=E,timeout=10);checks[name]={'ldd_stdout':x.stdout,'ldd_stderr':x.stderr,'returncode':x.returncode}
receipt={'all_retained_file_bytes_verified':True,'scp_expanded_symlinks_verified_content':expanded,'dependency_checks':checks,'free_bytes':shutil.disk_usage(r).free,'load_average':os.getloadavg(),'prior_readonly_preflight_failures':['Manifest absent while transfer still active, before any runtime execution.','Initial manifest lookup did not normalize relative documentation symlink ../; no runtime execution. Resolved by canonical POSIX path lookup, all184files checked.']}
(r/'runtime-preflight.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
