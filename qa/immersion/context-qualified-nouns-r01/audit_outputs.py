"""Read-only support binding, paired emission census, and exposed error follow-up."""
from common import *
import sqlite3
start=time.monotonic();os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});resource.setrlimit(resource.RLIMIT_AS,(1024**3,)*2);signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError()));signal.alarm(120)
p=json.loads((R/'protocol.json').read_text());look=json.loads((R/'prepare/lookup.json').read_text());data=json.loads(pathlib.Path(p['inputs']['dataset']['path']).read_text());rows={x['id']:x for x in data['rows']};db=sqlite3.connect('file:'+p['inputs']['evidence']['path']+'?mode=ro&immutable=1',uri=True);checks=collections.Counter();tok=tokenizer(p['inputs']['tokenizer']['path']);bindings={}
for name in ['dataset','evidence','catalog','trace']:
 assert sha(p['inputs'][name]['path'])==p['inputs'][name]['sha256'];bindings[name]=p['inputs'][name]['sha256']
for key,rule in look['rules'].items():
 assert key==enc([rule['source_key'],rule['focus_offset'],rule['tokens']]);assert rule['id']==digest(key)
 for face,ids in rule['support_rows'].items():
  comps=set()
  for ident in ids:
   row=rows[ident];assert row['split']=='train' and row['pool']=='explicit' and row['key']==rule['source_key'] and face in row['targets'];e=data['endpoints'][row['endpoint']];vals=[norm(t[0]) for t in tok(e['text'])];assert key in {k for k,_,_ in windows(row['key'],vals,row['focus_index'])};comps.add(row['component']);checks['support_rows_checked']+=1
  assert sorted(comps)==rule['support_components'][face]
 for head,ids in rule['admissible_head_rows'].items():
  assert len({rows[i]['component'] for i in ids})>=2
  assert look['original_head_records'][head]['target_face']==rule['target']
  for ident in ids:
   refs=look['train_rows'][ident]['valid_heads_by_face'][rule['target']][head]
   for ref in refs:
    d=json.loads(db.execute('select data from objects where id=?',(ref,)).fetchone()[0]);sf=data['dictionary_forms'][d['source_form_ref']];tf=data['dictionary_forms'][d['target_form_ref']];link=[sf['form_id'],tf['form_id'],d['source_term']['term_id'],d['target_term']['term_id']];assert link in look['original_override_links'][head];assert d['head']==head and ref in rows[ident]['targets'][rule['target']]['relation_refs'];assert d['original_form_number_term_eligible'] and d['both_exact_form_roles_noun'] and not d['exact_focus_reasons'] and not d['original_envelope_reasons'];checks['exact_head_relation_checks']+=1
 checks['rules_checked']+=1
changes=[];diagnostics=[]
with gzip.open(p['inputs']['trace']['path'],'rt') as f,gzip.open(R/'project/decisions.jsonl.gz','rt') as g:
 for a,b in zip(f,g,strict=True):
  t=json.loads(a);q=json.loads(b);assert t['id']==q['id'];cs=t['candidates']
  def values(d):return {enc([cs[i]['focus_utf16'],cs[i]['target'],cs[i]['reading']]):{'index':i,'head_id':cs[i]['head_id'],'focus_utf16':cs[i]['focus_utf16'],'source':cs[i]['source'],'target':cs[i]['target'],'reading':cs[i]['reading']} for i in d['selected_indices']}
  for known in KNOWN:
   qq=values(q['qualified'][known])
   for arm,parent in [('baseline','baseline'),('unrestricted','experimental')]:
    old=values(t['decisions'][known][parent]);added=[qq[x] for x in sorted(qq.keys()-old.keys())];lost=[old[x] for x in sorted(old.keys()-qq.keys())]
    if added or lost:changes.append({'id':t['id'],'known':known,'comparison':'qualified_vs_'+arm,'added':added,'lost':lost})
  if any(c['source'].casefold()=='fall' and c['target']=='caída' for c in cs) or 'dragon ball' in t['text'].casefold():diagnostics.append({'id':t['id'],'text':t['text'],'masks':t['source_masks'],'gates':q['gates'],'candidates':cs,'old':t['decisions'],'qualified':q['qualified']})
 db.close()
out=R/'closure-audit';out.mkdir(exist_ok=False)
for name,value in [('emission-changes.json',changes),('exposed-diagnostics.json',diagnostics)]:
 raw=(enc(value)+'\n').encode();assert len(raw)<8*M;(out/name).write_bytes(raw)
r={'complete':True,'input_hashes':bindings,'protocol_sha256':sha(R/'protocol.json'),'lookup_sha256':sha(R/'prepare/lookup.json'),'code_sha256':sha(__file__),'checks':dict(checks),'diagnostic_messages':len(diagnostics),'change_rows':len(changes),'seconds':time.monotonic()-start,'VmHWM_bytes':int(next(x.split()[1] for x in pathlib.Path('/proc/self/status').read_text().splitlines() if x.startswith('VmHWM:')))*1024,'outputs':{f.name:{'bytes':f.stat().st_size,'sha256':sha(f)} for f in out.iterdir()}}
(out/'receipt.json').write_text(enc(r)+'\n');print(enc(r))
