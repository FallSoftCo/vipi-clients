import urllib.request,hashlib,json,time,shutil,socket
from pathlib import Path
assert socket.gethostname()=='fallsoft-production-20261106'
w=Path('/srv/fallsoft/staging/vipi-bilingual-occurrence-roles-20261109-r01');o=w/'assets';o.mkdir(parents=True,exist_ok=False)
r={'started':time.time(),'files':{},'complete':False}
try:
 assert shutil.disk_usage(w).free>8*1024**3+64*1024**2
 base='https://downloads.apache.org/opennlp/models/ud-models-1.3/';name='opennlp-es-ud-gsd-pos-1.3-2.5.4.bin'
 for n in [name+'.sha512',name+'.asc',name,'LICENSE','README']:
  url=base+n
  with urllib.request.urlopen(url,timeout=30) as response:data=response.read(32*1024**2+1);assert len(data)<=32*1024**2
  (o/n).write_bytes(data);r['files'][n]={'url':url,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
 expected=(o/(name+'.sha512')).read_text().split()[0];actual=hashlib.sha512((o/name).read_bytes()).hexdigest();assert expected==actual;r.update(complete=True,sha512=actual,license='Official LICENSE retained; Apache-2.0 model distribution. Corpus attribution retained in README.',signature_downloaded_not_verified=True)
except BaseException as e:r['error']=repr(e);raise
finally:
 r['seconds']=time.time()-r['started'];(w/'acquisition-receipt.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
