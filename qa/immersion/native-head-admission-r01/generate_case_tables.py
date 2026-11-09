import pathlib,sys,unicodedata,json,hashlib,base64,time
assert sys.version_info[:3]==(3,12,6) and unicodedata.unidata_version=='15.0.0'
p=pathlib.Path(__file__).parent;start=time.monotonic()
def ranges(predicate):
 out=[]
 for cp in range(0x110000):
  if 0xD800<=cp<=0xDFFF or not predicate(chr(cp)):continue
  if out and out[-1][1]+1==cp:out[-1][1]=cp
  else:out.append([cp,cp])
 return out
t={'unicode_version':'15.0.0','lower':ranges(str.islower),'upper':ranges(str.isupper),'title':ranges(str.istitle)}
raw=json.dumps(t,separators=(',',':')).encode();h=hashlib.sha256(raw).hexdigest()
s='// Pinned Python3.12.6/Unicode15.0.0 scalar predicates. Generated; no OS case-property fallback.\nenum FrozenSourceCaseTables {\n static let sha256 = "'+h+'"\n static let base64 = "'+base64.b64encode(raw).decode()+'"\n}\n'
with (p/'FrozenSourceCaseTables.swift').open('x') as f:f.write(s)
cases=['dog','DOG','Dog','café','Straße','ß','ǅ','ǆ','ª','ᾳ','中文','123','dog2','dog’s','\u0345','İ','ı','ﬃ'];fixture=[{'source':x,'islower':x.islower(),'first_isupper':x[:1].isupper()} for x in cases]
r={'runtime':sys.version,'unicode':unicodedata.unidata_version,'seconds':time.monotonic()-start,'table_bytes':len(raw),'table_sha256':h,'source_sha256':hashlib.sha256(s.encode()).hexdigest(),'generator_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),'controls':fixture}
(p/'case-table-receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k!='controls'}))
