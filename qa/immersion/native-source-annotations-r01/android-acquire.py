import urllib.request,hashlib,json,shutil,time,os
from pathlib import Path
ROOT=Path('/home/ai/Development/investigations/vipi-android-source-annotations-20261108-r01')
os.umask(0o077)
start=time.monotonic(); receipts=[]
def get(url,name):
    assert time.monotonic()-start<180
    assert shutil.disk_usage(ROOT).free>=8589934592
    assert sum(p.stat().st_size for p in ROOT.rglob('*') if p.is_file())<33554432
    with urllib.request.urlopen(url,timeout=20) as r: b=r.read(8*1024*1024+1)
    assert len(b)<=8*1024*1024
    (ROOT/name).write_bytes(b)
    return b
base='https://downloads.apache.org/opennlp/models/ud-models-1.3/'
items=[(base+f'opennlp-en-ud-ewt-{s}-1.3-2.5.4.bin','sha256') for s in ('sentence','tokens','pos')]
items += [('https://repo.maven.apache.org/maven2/org/apache/opennlp/opennlp-tools/2.5.10/opennlp-tools-2.5.10.jar','sha512'),('https://repo.maven.apache.org/maven2/org/slf4j/slf4j-api/2.0.18/slf4j-api-2.0.18.jar','sha512')]
try:
    for url,alg in items:
        name=url.rsplit('/',1)[1]; b=get(url,name); checksum=get(url+'.'+alg,name+'.'+alg).decode().split()[0]
        actual=hashlib.new(alg,b).hexdigest(); assert actual==checksum,(name,actual,checksum)
        sig='retained'
        try: get(url+'.asc',name+'.asc')
        except Exception as e: sig=str(e)
        receipts.append(dict(url=url,file=name,bytes=len(b),checksum_algorithm=alg,checksum=actual,publisher_checksum_match=True,signature=sig))
    for url,name in [(base+'LICENSE','models-LICENSE'),(base+'README','models-README'),('https://downloads.apache.org/opennlp/KEYS','apache-KEYS'),('https://raw.githubusercontent.com/apache/opennlp/opennlp-2.5.10/LICENSE','tools-LICENSE'),('https://raw.githubusercontent.com/apache/opennlp/opennlp-2.5.10/NOTICE','tools-NOTICE'),('https://raw.githubusercontent.com/qos-ch/slf4j/v_2.0.18/LICENSE.txt','slf4j-LICENSE')]:
        try: get(url,name)
        except Exception as e: receipts.append(dict(url=url,error=str(e)))
finally:
    (ROOT/'acquisition.json').write_text(json.dumps({'receipts':receipts,'elapsed_seconds':time.monotonic()-start},indent=2)+'\n')
    print(json.dumps(receipts,indent=2))
