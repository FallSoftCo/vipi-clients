import collections,gzip,hashlib,json,sqlite3,resource,os
from pathlib import Path
Q=Path(__file__).resolve().parent;W=Path('/home/ai/Development/investigations/vipi-bilingual-occurrence-roles-20261109-r01');A=Path('/home/ai/Development/investigations/vipi-lexical-choice-evidence-20261109-r01/occurrences-r02/audit-evidence.json');P=Path('/home/ai/Development/investigations/vipi-tatoeba-domain-comparison-20261108-r01/remote-evidence/outputs/fetch/en-es-pairs.jsonl.gz')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def enc(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def write(n,v):
 with (W/n).open('x') as f:f.write(enc(v)+'\n')
os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});resource.setrlimit(resource.RLIMIT_AS,(1024**3,)*2)
assert sha(A)=='e4d7b855aae253f9ea53c00aa635578c63dab469ff739d3e766f223764135512';assert sha(P)=='4eabc120af4d8cf31a8ba85709d7e9408cc06623fa585b0f3355e915eb6b8268'
d=json.loads(A.read_text());pairs=d['full_pairs'];occ=collections.defaultdict(list)
for o in d['occurrences']:occ[o['pair_id']].append(o)
controls=[('order_verb','I did not order this.',['order']),('order_noun',"Here's your order.",['order']),('fall_descent',"They're celebrating the fall of the wall.",['fall']),('fall_season','We moved to New York last fall.',['fall','New','York']),('name_span','This is the boy whose name is Tom Fisher.',['name','Tom','Fisher']),('contraction',"Tom can't even write his own name.",['name','Tom']),('inflected_nouns','Tom made a list of places he wants to visit.',['places']),('compound','In many places in China, there were temples of the dragon-king.',['dragon','king'])]
needed={x[1] for x in controls};found={}
with gzip.open(P,'rt') as f:
 for line in f:
  x=json.loads(line)
  if x['source']['text'] in needed:found.setdefault(x['source']['text'],[]).append(x)
def rank(p):return (hashlib.sha256(str(p['source']['id']).encode()).hexdigest(),p['source']['id'],p['target']['id'])
selected=[];used=set()
for label,text,focus in controls:
 p=min(found[text],key=rank);pid=p['pair_id'];p=pairs.get(pid,p);selected.append({'stratum':'development','control':label,'pair_id':pid,'pair':p,'extra_source_tokens':[i for i,t in enumerate(p['source']['tokens']) if t['text'] in focus]});used.add(p['source']['id'])
db=sqlite3.connect('file:/home/ai/Development/investigations/vipi-immersion-reconciliation-20261107-r01/noun-boundary-arms/d-en.sqlite?mode=ro&immutable=1',uri=True);db.execute('PRAGMA query_only=ON');amb={};cache={}
for pid,p in pairs.items():
 evidence=[]
 for o in occ[pid]:
  if not o['all_supported_link_refs']:continue
  a,b=o['source_tokens']
  if b-a!=1:continue
  word=p['source']['tokens'][a]['text'].lower()
  if word not in cache:cache[word]=list(db.execute("SELECT DISTINCT l.id,l.pos FROM surfaces s JOIN lexemes l ON l.id=s.lexeme WHERE s.normalized=? AND l.pos IN ('noun','verb') ORDER BY l.id",(word,)))
  if {r[1] for r in cache[word]}=={'noun','verb'}:evidence.append({'source_index':a,'dictionary_noun_verb_entries':cache[word]})
 if evidence:amb[pid]=evidence
db.close()
# Reserve ambiguity cases first; general cases then exclude these endpoints.
for pid,p in sorted(pairs.items(),key=lambda x:rank(x[1])):
 if pid in amb and p['source']['id'] not in used:
  selected.append({'stratum':'dictionary_role_ambiguity','pair_id':pid,'pair':p,'ambiguity_evidence':amb[pid],'extra_source_tokens':[]});used.add(p['source']['id'])
  if sum(x['stratum']=='dictionary_role_ambiguity' for x in selected)==8:break
for pid,p in sorted(pairs.items(),key=lambda x:rank(x[1])):
 if p['source']['id'] not in used:
  selected.append({'stratum':'source_hash_diagnostic','pair_id':pid,'pair':p,'extra_source_tokens':[]});used.add(p['source']['id'])
  if len(selected)==32:break
assert len(selected)==32 and len(used)==32
for x in selected:
 x['retained_occurrences']=occ[x['pair_id']];p=x['pair']
 for side in ('source','target'):
  for t in p[side]['tokens']:
   a,b=t['codepoints'];assert p[side]['text'][a:b]==t['text'];assert [len(p[side]['text'][:z].encode('utf-16-le'))//2 for z in (a,b)]==t['utf16']
 x['pair_sha256']=hashlib.sha256(enc(p).encode()).hexdigest()
write('selection-freeze.json',{'inputs':{str(A):sha(A),str(P):sha(P)},'script_sha256':sha(Path(__file__)),'model_output_seen':False,'ordering':'Reserve eight explicit development controls, eight hash-ordered supported noun-focus forms with dictionary noun+verb entries, then16hash-ordered audit sources; distinct source IDs throughout. Tie target ID. All retained candidate occurrences included.','cases':selected,'missing_alignment_indices':[x['pair']['index'] for x in selected if 'forward_links' not in x['pair']]})
print('selection',sha(W/'selection-freeze.json'),'missing',[(x['pair'].get('index'),x['pair_id']) for x in selected if 'forward_links' not in x['pair']])
