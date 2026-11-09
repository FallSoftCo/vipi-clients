import hashlib,json,os,platform,posixpath,shutil,socket,subprocess,tarfile,time,urllib.request
from pathlib import Path
R=Path('/srv/fallsoft/staging/vipi-bilingual-occurrence-roles-20261109-r01');W=R/'runtime-corretto-r02'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def main():
 assert socket.gethostname()=='fallsoft-production-20261106' and platform.machine()=='x86_64';W.mkdir(exist_ok=False);os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});os.nice(10);start=time.monotonic();receipt={'complete':False,'script_sha256':sha(Path(__file__))}
 try:
  assert shutil.disk_usage(R).free>8*1024**3+1024**3
  name='amazon-corretto-21-x64-linux-jdk.tar.gz';url='https://corretto.aws/downloads/latest/'+name;checksum_url='https://corretto.aws/downloads/latest_sha256/'+name
  with urllib.request.urlopen(checksum_url,timeout=30) as response:checksum=response.read(4096);checksum_final=response.url
  (W/'official-checksum.txt').write_bytes(checksum);expected=checksum.decode().split()[0];assert len(expected)==64
  archive=W/name;receipt.update(archive_path=str(archive),download_url=url,checksum_url=checksum_url,checksum_resolved_url=checksum_final,official_sha256=expected,official_documentation='https://docs.aws.amazon.com/corretto/latest/corretto-21-ug/downloads-list.html')
  with urllib.request.urlopen(url,timeout=30) as response,archive.open('xb') as out:
   receipt['resolved_url']=response.url;total=0
   while True:
    b=response.read(1024**2)
    if not b:break
    total+=len(b);assert total<=256*1024**2;out.write(b)
  assert sha(archive)==expected
  with tarfile.open(archive,'r:gz') as tar:
   members=tar.getmembers();tops={m.name.split('/')[0] for m in members};assert len(tops)==1;top=next(iter(tops));total=sum(m.size for m in members if m.isfile());assert total<768*1024**2
   for m in members:
    assert not m.name.startswith('/') and '..' not in Path(m.name).parts and (m.isfile() or m.isdir() or m.issym() or m.islnk())
    if m.issym() or m.islnk():
     target=posixpath.normpath(posixpath.join(posixpath.dirname(m.name),m.linkname) if m.issym() else m.linkname);assert not m.linkname.startswith('/') and (target==top or target.startswith(top+'/'))
   preflight={'archive_sha256':sha(archive),'members':len(members),'uncompressed_regular_bytes':total,'top':top,'types':sorted({repr(m.type) for m in members}),'safe_paths_and_links':True};(W/'archive-preflight.json').write_text(json.dumps(preflight,indent=2)+'\n');tar.extractall(W,filter='data')
  home=W/top;versions={}
  for name in ('java','javac'):
   run=subprocess.run([str(home/'bin'/name),'-version'],capture_output=True,text=True,timeout=15);assert run.returncode==0;versions[name]=run.stdout+run.stderr
  actual=sum(p.stat().st_size for p in home.rglob('*') if p.is_file() and not p.is_symlink());licenses={str(p.relative_to(home)):sha(p) for p in home.rglob('*') if p.is_file() and ('LICENSE' in p.name or 'ASSEMBLY_EXCEPTION'==p.name)}
  receipt.update(complete=True,jdk_home=str(home),versions=versions,archive_sha256=sha(archive),measured_extracted_regular_bytes=actual,retained_runtime_total_bytes=sum(p.stat().st_size for p in W.rglob('*') if p.is_file() and not p.is_symlink()),license_files=licenses,license='GPLv2 with Classpath Exception; exact included notices retained')
 except BaseException as e:receipt['error']=repr(e);raise
 finally:
  receipt['seconds']=time.monotonic()-start;(W/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
if __name__=='__main__':main()
