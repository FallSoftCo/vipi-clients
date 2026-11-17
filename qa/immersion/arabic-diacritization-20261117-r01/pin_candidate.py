"""Research-only: download exact verified artifacts into an owned native-Mac directory."""
from pathlib import Path, PurePosixPath
import hashlib,json,os,platform,shutil,sys,urllib.request,zipfile

ROOT=Path(__file__).resolve().parent
REV='ff8783fff6f6986929d8986983279d2f307d7bed'
MAX_TOTAL=150*1024**2
ARTIFACTS={
 'model.onnx':(f'https://huggingface.co/ichkil/ichkil/resolve/{REV}/model.onnx',22284311,'9779e1aca89cebc77a9b92037b7d700c422cdf6c3774d4883f4652f641f3f705'),
 'onnxruntime.whl':('https://files.pythonhosted.org/packages/6f/a4/480cd367bc135dd9951c89d461cc6af6be9302cd2ce91e231f6cb0e7ee1b/onnxruntime-1.32.0-cp312-cp312-macosx_14_0_arm64.whl',22519308,'d52510bbbcc880c13b826f7d75cdf33ac5cf0bb864d960000fc29ce73f0cb83e'),
 'numpy.whl':('https://files.pythonhosted.org/packages/8a/92/6de34324a266b73c04ba977db5864b9016500076b26f09078a565f527d34/numpy-2.5.5-cp312-cp312-macosx_14_0_arm64.whl',5513680,'a3856a97e48ed8371c680fb04120b99fbcc29f2076ebe6dc3deb34f77947c5ca'),
}

def used():return sum(p.stat().st_size for p in ROOT.rglob('*') if p.is_file())
def download(name,url,size,expected=None):
 dest=ROOT/name
 if dest.exists():
  raw=dest.read_bytes()
  if len(raw)!=size or expected and hashlib.sha256(raw).hexdigest()!=expected:raise RuntimeError('Existing artifact identity mismatch: '+name)
  return raw
 if used()+size>MAX_TOTAL or shutil.disk_usage(ROOT).free<4*1024**3+MAX_TOTAL:raise RuntimeError('Artifact reserve exceeded')
 part=dest.with_suffix(dest.suffix+'.part')
 if part.exists():raise RuntimeError('Inspect retained partial artifact before retry: '+str(part))
 digest=hashlib.sha256();count=0
 with urllib.request.urlopen(url,timeout=60) as response,part.open('xb') as out:
  while chunk:=response.read(1024*1024):
   count+=len(chunk)
   if count>size:raise RuntimeError('Oversized artifact')
   out.write(chunk);digest.update(chunk)
  out.flush();os.fsync(out.fileno())
 if count!=size or expected and digest.hexdigest()!=expected:raise RuntimeError('Downloaded identity mismatch: '+name)
 part.rename(dest)
 return dest.read_bytes()

if platform.system()!='Darwin' or platform.machine()!='arm64':raise RuntimeError('Owned native arm64 Mac only')
files={}
for name,(url,size,expected) in ARTIFACTS.items():
 raw=download(name,url,size,expected);files[name]={'url':url,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()};print(name,len(raw),flush=True)
for name in ['config.json','manifest.json','SHA256SUMS','README.md']:
 url=f'https://huggingface.co/ichkil/ichkil/resolve/{REV}/{name}'
 # Small metadata is pinned by immutable source commit, then content-hashed.
 dest=ROOT/name
 if not dest.exists():
  raw=urllib.request.urlopen(url,timeout=30).read(128*1024+1)
  if len(raw)>128*1024:raise RuntimeError('Oversized metadata')
  dest.write_bytes(raw)
 raw=dest.read_bytes();files[name]={'url':url,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
runtime=ROOT/'runtime';runtime.mkdir(exist_ok=True)
metadata={}
for name in ['onnxruntime.whl','numpy.whl']:
 with zipfile.ZipFile(ROOT/name) as archive:
  pending=[x for x in archive.infolist() if not (runtime/x.filename).exists()]
  if used()+sum(x.file_size for x in pending)>MAX_TOTAL:raise RuntimeError('Unpacked runtime peak exceeds 150MiB')
  for item in archive.infolist():
   rel=PurePosixPath(item.filename)
   if rel.is_absolute() or '..' in rel.parts or (item.external_attr>>16)&0o170000==0o120000:raise RuntimeError('Unsafe wheel member')
  for item in pending:archive.extract(item,runtime)
  for item in archive.infolist():
   if item.filename.endswith('.dist-info/METADATA'):
    text=archive.read(item).decode();metadata[name]=[line for line in text.splitlines() if line.startswith(('Name:','Version:','Requires-Dist:'))]
receipt={'schema':'vipi-arabic-candidate-pin-1','model_revision':REV,'inference_source_repo':'Ichkil/ichkil-python','inference_source_commit':'380cf89465fafa6341ab007532101e299d20bb53','training_source_repo':'https://github.com/Ichkil/ichkil','training_source_http_status':404,'license_evidence':'Model card explicitly declares MIT for ONNX/config; exact inference-client MIT license retained separately, no standalone model LICENSE file supplied.','runtime_purpose':'Isolated native CPU research process only; no app dependency or global installation','artifacts':files,'wheel_metadata':metadata,'total_logical_bytes':used(),'max_bytes':MAX_TOTAL,'platform':platform.platform()}
(ROOT/'pin-receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'total_bytes':used(),'metadata':metadata}),flush=True)
