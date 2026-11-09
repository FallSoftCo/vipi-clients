import collections,hashlib,json,os,re,resource,signal,sqlite3,sys,time,unicodedata
from pathlib import Path
R=Path('/srv/fallsoft/staging/vipi-taskmaster-structural-evidence-20261109-r01');load=lambda p:json.loads(Path(p).read_text());sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();norm=lambda s:unicodedata.normalize('NFC',s).casefold()
start=time.monotonic();resource.setrlimit(resource.RLIMIT_AS,(1<<30,)*2);os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});os.nice(10);signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('parse120s')));signal.alarm(120)
out=R/'comparison';out.mkdir(exist_ok=False);receipt={'complete':False,'code_sha256':sha(__file__),'engine_receipt_sha256':sha(R/'engine/receipt.json')}
try:
 er=load(R/'engine/receipt.json');assert er['complete'] and er['messages']==200
 for name,v in er['files'].items():assert sha(R/'engine'/name)==v['sha256']
 maps={r['id']:r for r in load(R/'engine/mapping.json')};roles=load(R/'inputs/role-comparison.json');inputs={r['id']:r for r in load(R/'inputs/inputs-200.json')['cases']};db=sqlite3.connect('file:/srv/fallsoft/staging/vipi-context-key-expansion-20261109-r01/inputs/d-es.sqlite?mode=ro&immutable=1',uri=True);db.row_factory=sqlite3.Row
 tags={'n':'noun','np':'proper_name','vblex':'verb','vaux':'verb','vbser':'verb','vbhaver':'verb','vbmod':'verb','adj':'adj','adv':'adv','ij':'intj','num':'num','prn':'pron','det':'det','pr':'prep','cnjcoo':'conj','cnjsub':'conj'}
 def analysis(a):
  t=re.findall(r'<([^>]+)>',a);return {'raw':a,'lemma':re.sub(r'<[^>]*>','',a),'tags':t,'pos':tags.get(t[0]) if t else None,'unknown':a.startswith(('*','@','#')) or '+' in a}
 rows=[]
 for edge in roles['scope_edges']:
  m=maps[edge['id']];r={'id':edge['id'],'source_utf16':edge['source_utf16'],'target_utf16':edge['target_utf16'],'apple_comparison':edge['comparison'],'original_edge_alternatives':edge['edge_alternatives'],'mapping_checks':m['sequence_identity']};indices=[i for i,s in enumerate(m['source_spans']) if s==edge['source_utf16']]
  if not m['mapped'] or len(indices)!=1:r['status']='source_mapping_unavailable'
  else:
   i=indices[0];src=analysis(m['source_analyses'][i]);r.update(status='mapped',source_analysis=src,before=[analysis(s) for s in m['before'][i]],after=[analysis(s) for s in m['after'][i]])
   r['source_pos_comparison']='unassessed' if src['unknown'] or src['pos'] is None else 'compatible' if any(e['dictionary_pos']==src['pos'] for e in edge['edge_alternatives']) else 'incompatible'
   target=[]
   for tid in sorted({e['edge']['target_lexeme'] for e in edge['edge_alternatives']}):
    d=dict(db.execute('SELECT * FROM lexemes WHERE id=?',(tid,)).fetchone());target.append(d)
   r['existing_target_lexemes']=target
   r['lemma_comparison']={}
   for stage in ['before','after']:
    choices=r[stage];first=choices[0] if choices else None
    r['lemma_comparison'][stage]='unavailable' if first is None or first['unknown'] else 'same_lemma' if any(norm(first['lemma'])==norm(t['headword']) for t in target) else 'different_lemma'
   r['first_choice_changed']=m['before'][i][:1]!=m['after'][i][:1];r['alternatives_changed']=m['before'][i]!=m['after'][i]
  rows.append(r)
 # Transfer traces are retained, but rule-match lines alone are NOT committed chunk/target alignment.
 traces=[]
 for cid,m in maps.items():
  base=R/'engine'/m['stage_prefix'];s=(base/'chunk.stderr').read_text();lines=[l for l in s.splitlines() if 'apertium-transfer: Rule ' in l];consume=[l for l in s.splitlines() if 'num_words_to_consume:' in l];traces.append({'id':cid,'rule_match_attempts':lines,'consumption_trace':consume,'exact_source_mapping':m['mapped'],'trace_sha256':sha(base/'chunk.stderr'),'chunk_sha256':sha(base/'chunk.raw'),'rule_matches_are_not_semantic_approval':True,'automatic_source_to_generated_target_alignment':False})
 index={(r['id'],tuple(r['source_utf16']),tuple(r['target_utf16'])):r for r in rows};selected=[]
 for old in roles['selected_spans']:
  r=index.get((old['id'],tuple(old['span']['source_utf16']),tuple(old['span']['target_utf16'])));new=dict(old);new['apertium']=None if r is None else {k:r[k] for k in ['status','source_pos_comparison','lemma_comparison','first_choice_changed'] if k in r};selected.append(new)
 summary={'messages':200,'scope_edges':len(rows),'message_sequence_mapped':sum(m['mapped'] for m in maps.values()),'edge_status':dict(collections.Counter(r['status'] for r in rows)),'source_pos':dict(collections.Counter(r.get('source_pos_comparison','unavailable') for r in rows)),'lemma_comparison':{s:dict(collections.Counter(r.get('lemma_comparison',{}).get(s,'mapping_unavailable') for r in rows)) for s in ['before','after']},'first_changes_mapped_edges':sum(r.get('first_choice_changed',False) for r in rows),'alternative_changes_mapped_edges':sum(r.get('alternatives_changed',False) for r in rows),'all_stream_first_changes':sum(sum(b[:1]!=a[:1] for b,a in zip(m['before'],m['after'])) for m in maps.values() if len(m['before'])==len(m['after'])),'all_stream_alternative_changes':sum(sum(b!=a for b,a in zip(m['before'],m['after'])) for m in maps.values() if len(m['before'])==len(m['after'])),'chunk_rule_match_attempts':sum(len(t['rule_match_attempts']) for t in traces),'methods':'default versus LRX; target lemma agreement is neither form nor sense approval; no new emissions'}
 result={'summary':summary,'edges':rows,'selected':selected,'transfer_traces':traces}
 for name,data in [('comparison.json',result),('summary.json',summary)]:
  b=(json.dumps(data,ensure_ascii=False,indent=2)+'\n').encode();assert sum(f.stat().st_size for f in (R/'engine').rglob('*') if f.is_file())+sum(f.stat().st_size for f in out.rglob('*') if f.is_file())+len(b)<64*(1<<20);(out/name).write_bytes(b)
 receipt['complete']=True
except BaseException as e:receipt['error']=repr(e)
finally:
 signal.alarm(0);receipt.update(seconds=time.monotonic()-start,VmHWM_bytes=int(next(x.split()[1] for x in Path('/proc/self/status').read_text().splitlines() if x.startswith('VmHWM:')))*1024,outputs={str(f.relative_to(out)):{'bytes':f.stat().st_size,'sha256':sha(f)} for f in out.rglob('*') if f.is_file()});(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
if not receipt['complete']:sys.exit(1)
