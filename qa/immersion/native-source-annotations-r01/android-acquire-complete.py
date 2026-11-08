import urllib.request,hashlib,json,shutil,os,subprocess,zipfile
from pathlib import Path
os.umask(0o077)
p=Path('/home/ai/Development/investigations/vipi-android-source-annotations-20261108-r01')
assert shutil.disk_usage(p).free>=8589934592
receipts=[]
def fetch(u,n):
    b=urllib.request.urlopen(u,timeout=20).read(8*1024*1024+1);assert len(b)<=8*1024*1024
    (p/n).write_bytes(b);return b
for n,u,alg in [('opennlp-tools-2.5.10.jar','https://repo.maven.apache.org/maven2/org/apache/opennlp/opennlp-tools/2.5.10/','sha1'),('slf4j-api-2.0.18.jar','https://repo.maven.apache.org/maven2/org/slf4j/slf4j-api/2.0.18/','sha512')]:
    b=(p/n).read_bytes() if (p/n).exists() else fetch(u+n,n)
    expected=fetch(u+n+'.'+alg,n+'.'+alg).decode().strip();assert hashlib.new(alg,b).hexdigest()==expected
    fetch(u+n+'.asc',n+'.asc')
    receipts.append(dict(url=u+n,file=n,bytes=len(b),publisher_checksum_algorithm=alg,publisher_checksum=expected,checksum_match=True,local_sha256=hashlib.sha256(b).hexdigest()))
for u,n in [('https://downloads.apache.org/opennlp/models/ud-models-1.3/LICENSE','models-LICENSE'),('https://downloads.apache.org/opennlp/models/ud-models-1.3/README','models-README'),('https://downloads.apache.org/opennlp/KEYS','apache-KEYS'),('https://raw.githubusercontent.com/apache/opennlp/opennlp-2.5.10/LICENSE','tools-LICENSE'),('https://raw.githubusercontent.com/apache/opennlp/opennlp-2.5.10/NOTICE','tools-NOTICE')]: fetch(u,n)
with zipfile.ZipFile(p/'slf4j-api-2.0.18.jar') as z:
    for n in z.namelist():
        if 'LICENSE' in n or 'NOTICE' in n: (p/('slf4j-'+Path(n).name)).write_bytes(z.read(n))
gpg=p/'gnupg';gpg.mkdir(mode=0o700,exist_ok=True)
r=subprocess.run(['gpg','--homedir',str(gpg),'--batch','--import',str(p/'apache-KEYS')],capture_output=True,text=True,timeout=20);(p/'gpg-import.log').write_text(r.stdout+r.stderr)
for sig in sorted(p.glob('*.asc')):
    r=subprocess.run(['gpg','--homedir',str(gpg),'--batch','--status-fd','1','--verify',str(sig),str(sig)[:-4]],capture_output=True,text=True,timeout=20)
    (p/(sig.name+'.verify.log')).write_text(r.stdout+r.stderr)
    receipts.append(dict(signature=sig.name,returncode=r.returncode,validsig=next((s for s in r.stdout.splitlines() if 'VALIDSIG' in s),None),note='Apache publisher KEYS establish key provenance; key owner trust is not independently certified. SLF4J key absent if NO_PUBKEY.'))
(p/'acquisition-completed.json').write_text(json.dumps(receipts,indent=2)+'\n')
assert sum(x.stat().st_size for x in p.rglob('*') if x.is_file())<33554432
print(json.dumps(receipts,indent=2))
