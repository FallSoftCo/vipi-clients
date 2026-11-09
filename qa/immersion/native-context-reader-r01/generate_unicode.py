import sys,unicodedata as u,re,json,hashlib,time
start=time.monotonic();assert u.unidata_version=='15.0.0'
def ranges(values):
 out=[]
 for x in values:
  if out and out[-1][1]+1==x:out[-1][1]=x
  else:out.append([x,x])
 return out
assigned=[];alnum=[];alpha=[];space=[];fold=[]
for cp in range(0x110000):
 if 0xD800<=cp<=0xDFFF:continue
 c=chr(cp)
 if u.category(c)!='Cn':assigned.append(cp)
 if c.isalnum():alnum.append(cp)
 if c.isalpha():alpha.append(cp)
 if c.isspace():space.append(cp)
 if c.casefold()!=c:fold.append([cp,[ord(v) for v in c.casefold()]])
 # Frozen re semantics are alphanumeric plus underscore.
 assert bool(re.fullmatch(r'\w',c))==(c.isalnum() or c=='_')
t={'unicode_version':u.unidata_version,'assigned':ranges(assigned),'alnum':ranges(alnum),'alpha':ranges(alpha),'space':ranges(space),'casefold':fold}
raw=json.dumps(t,separators=(',',':')).encode();sha=hashlib.sha256(raw).hexdigest()
probes=['my dog\'s bed','my dog’s bed','red, dog','red. dog','needs.it','a_b','Straße CAFÉ','cafe\u0301 dog','İ I ı i','Σ σ ς','ﬃ dog','K café','a\u001cb','a\u00a0b','😀 dog','𐐀 dog','中文 dog','Ａ dog','\u0301x','\u0378 dog','\U0001FAE8 dog','\U0001FAE9 dog']
pat=re.compile(r"[^\W_]+(?:['’][^\W_]+)*|[^\w\s]",re.UNICODE)
ps=[]
for s in probes:
 ts=[]
 for m in pat.finditer(s):
  ts.append({'text':m.group(),'range':[len(s[:m.start()].encode('utf-16-le'))//2,len(m.group().encode('utf-16-le'))//2],'normalized':' '.join(u.normalize('NFC',m.group()).casefold().split()),'has_alpha':any(c.isalpha() for c in ' '.join(u.normalize('NFC',m.group()).casefold().split()))})
 ps.append({'source':s,'supported':all(u.category(c)!='Cn' for c in s),'tokens':ts})
print(json.dumps({'tables':t,'table_sha256':sha,'table_bytes':len(raw),'probes':ps,'runtime':sys.version,'elapsed_seconds':time.monotonic()-start},ensure_ascii=True,separators=(',',':')))
