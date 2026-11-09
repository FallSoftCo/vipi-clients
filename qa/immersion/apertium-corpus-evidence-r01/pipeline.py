import collections,functools,gzip,hashlib,importlib.util,json,os,resource,shutil,signal,socket,sqlite3,subprocess,sys,time,unicodedata
from pathlib import Path
import stream_tools as stream
from form_role_join import form_role_evidence,mechanism_controls
R=Path('/srv/fallsoft/staging/vipi-apertium-corpus-evidence-20261109-r01');A=Path('/srv/fallsoft/staging/vipi-apertium-occurrence-roles-20261109-r01');MiB=1024**2

def enc(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(MiB),b''):h.update(b)
 return h.hexdigest()
def norm(text):return ' '.join(unicodedata.normalize('NFC', text).casefold().split())
def endpoint_key(e):return hashlib.sha256(json.dumps([e['language'],e['id'],e['text'],e['tokens']],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
def load(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def geometry(e):
 assert '\x00' not in e['text'],'embedded NUL'
 for t in e['tokens']:
  a,b=t['codepoints'];assert e['text'][a:b]==t['text'];assert [len(e['text'][:z].encode('utf-16-le'))//2 for z in (a,b)]==t['utf16']
def dbread(p):
 db=sqlite3.connect(Path(p).as_uri()+'?mode=ro&immutable=1',uri=True);db.row_factory=sqlite3.Row;db.execute('PRAGMA query_only=ON');db.execute('PRAGMA cache_size=-4096');return db
class Run:
 def __init__(self,stage):
  assert socket.gethostname()=='fallsoft-production-20261106';self.plan=json.loads((R/'execution-protocol.json').read_text());assert sha(__file__)==self.plan['scripts']['pipeline.py'];self.stage=stage;self.start=time.monotonic();self.out=R/('annotation-r01' if stage=='annotate' else 'join-r01');self.out.mkdir(exist_ok=False);self.receipt={'complete':False,'stage':stage,'protocol_sha256':sha(R/'execution-protocol.json')};self.limit=(32 if stage=='annotate' else 96)*MiB;self.last_progress=self.start
  os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});os.nice(10);resource.setrlimit(resource.RLIMIT_AS,((256 if stage=='annotate' else 1024)*MiB,)*2)
  def expired(*args):raise TimeoutError('300s stage bound')
  signal.signal(signal.SIGALRM,expired);signal.alarm(300);assert shutil.disk_usage(R).free>8*1024**3+160*MiB
 def verify(self,names):
  for name,h in self.plan['scripts'].items():assert sha(R/name)==h,name
  for name in names:
   b=self.plan['inputs'][name];assert sha(b['path'])==b['sha256'],name
 def path(self,name):return Path(self.plan['inputs'][name]['path'])
 def check(self):
  assert time.monotonic()-self.start<300;assert sum(p.stat().st_size for p in self.out.rglob('*') if p.is_file())<self.limit,'stage output bound; retain failure, no truncation'
 def progress(self,**values):
  if time.monotonic()-self.last_progress>=45:print(enc({'stage':self.stage,'elapsed':time.monotonic()-self.start,**values}),flush=True);self.last_progress=time.monotonic()
 def finish(self,error=None):
  self.receipt.update(complete=error is None,error=error,seconds=time.monotonic()-self.start,VmHWM_bytes=int(next(s.split()[1] for s in Path('/proc/self/status').read_text().splitlines() if s.startswith('VmHWM:')))*1024,outputs={str(p.relative_to(self.out)):{'bytes':p.stat().st_size,'sha256':sha(p)} for p in self.out.rglob('*') if p.is_file()});(self.out/'receipt.json').write_text(json.dumps(self.receipt,indent=2)+'\n');print(enc({k:v for k,v in self.receipt.items() if k!='outputs'}),flush=True)

def annotate(r):
 r.verify(['endpoint_inventory','pairs','apertium_protocol']);prior=json.loads(r.path('apertium_protocol').read_text())
 for name,h in prior['execution_assets'].items():assert sha(A/name)==h,name
 inventory=json.loads(r.path('endpoint_inventory').read_text())['endpoints'];selected_pairs={pid for v in inventory.values() for pid in v['pair_ids']};assert len(selected_pairs)==7115;selected_pair_count=0;all_pair_count=0;endpoints={};pair_seen=collections.defaultdict(list)
 with gzip.open(r.path('pairs'),'rt') as f:
  for line in f:
   p=json.loads(line);assert p['index']==all_pair_count;all_pair_count+=1
   if p['pair_id'] not in selected_pairs:continue
   selected_pair_count+=1
   for side in ('source','target'):
    e=p[side];k=endpoint_key(e)
    if k not in inventory:continue
    geometry(e);v=inventory[k];assert e['fingerprint']==v['fingerprint'] and e['record_sha256']==v['record_sha256'];assert hashlib.sha256(e['text'].encode()).hexdigest()==v['text_sha256'];assert hashlib.sha256(json.dumps(e['tokens'],sort_keys=True).encode()).hexdigest()==v['token_geometry_sha256'];pair_seen[k].append(p['pair_id']);endpoints[k]={'text':e['text'],'tokens':e['tokens'],'language':e['language'],'id':e['id']}
 assert len(endpoints)==14004 and all_pair_count==40000 and selected_pair_count==7115
 for k,v in inventory.items():assert pair_seen[k]==v['pair_ids'],k
 del pair_seen
 index=sqlite3.connect(r.out/'index.sqlite');index.execute('PRAGMA page_size=4096');index.execute('PRAGMA max_page_count=4096');index.execute('CREATE TABLE endpoints(key TEXT PRIMARY KEY,language TEXT,id INTEGER,text_sha TEXT,geometry_sha TEXT,deformat_offset INTEGER,deformat_bytes INTEGER,morph_offset INTEGER,morph_bytes INTEGER,morph_sha TEXT,tag_offset INTEGER,tag_bytes INTEGER,tag_sha TEXT) WITHOUT ROWID');env=os.environ.copy();env['LD_LIBRARY_PATH']=str(A/'root/usr/lib/x86_64-linux-gnu');env['LC_ALL']='C.UTF-8';files={n:(r.out/(n+'.raw')).open('xb') for n in ('deformat','morph','tag')};completed=0;batch_count=0;empty_suffixes=collections.Counter()
 def execute(command,value):
  assert b'\0' not in value or '-z' in command
  z=subprocess.run(command,input=value,capture_output=True,env=env,timeout=min(10,max(1,300-(time.monotonic()-r.start))));assert z.returncode==0,(command,z.returncode,z.stderr.decode());assert len(z.stdout)<8*MiB
  if z.stderr:
   with (r.out/'child-stderr.jsonl').open('a') as log:log.write(enc({'command':command,'stderr':z.stderr.decode()})+'\n')
  return z.stdout
 def save(name,data):
  fp=files[name];offset=fp.tell();fp.write(data);fp.write(b'\0');return offset,len(data)
 try:
  for language,direction in [('en','eng-spa'),('es','spa-eng')]:
   keys=sorted(k for k,e in endpoints.items() if e['language']==language)
   for begin in range(0,len(keys),32):
    batch=keys[begin:begin+32];deformatted=[];positions={}
    for k in batch:
     e=endpoints[k];value=execute([str(A/'root/usr/bin/apertium-destxt')],(e['text']+'\n').encode());assert b'\0' not in value;deformatted.append(value);positions[k]=save('deformat',value)
    value=b'\0'.join(deformatted)+b'\0';streams={}
    for stage,cmd in [('morph',[str(A/'root/usr/bin/lt-proc'),'-z',str(A/'root/usr/share/apertium/apertium-eng-spa'/(direction+'.automorf.bin'))]),('tag',[str(A/'root/usr/bin/apertium-tagger'),'-g','-p','-z',str(A/'root/usr/share/apertium/apertium-eng-spa'/(direction+'.prob'))])]:
     raw=execute(cmd,value);segments=raw.split(b'\0');assert len(segments)>=len(batch) and all(x==b'' for x in segments[len(batch):]),'nonempty surplus records';empty_suffixes[stage]+=len(segments)-len(batch);streams[stage]=segments[:len(batch)];value=raw
    for i,k in enumerate(batch):
     mo,ml=save('morph',streams['morph'][i]);to,tl=save('tag',streams['tag'][i]);e=endpoints[k];v=inventory[k];do,dl=positions[k];index.execute('INSERT INTO endpoints VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(k,language,e['id'],v['text_sha256'],v['token_geometry_sha256'],do,dl,mo,ml,hashlib.sha256(streams['morph'][i]).hexdigest(),to,tl,hashlib.sha256(streams['tag'][i]).hexdigest()));completed+=1
    index.commit();batch_count+=1
    for fp in files.values():fp.flush()
    r.check();r.progress(endpoints=completed,batches=batch_count)
  assert completed==14004;assert index.execute('SELECT COUNT(*) FROM endpoints').fetchone()[0]==14004
 finally:
  index.close()
  for fp in files.values():fp.close()
 r.receipt.update(endpoints=completed,batches=batch_count,tokens=sum(len(e['tokens']) for e in endpoints.values()),terminal_empty_split_segments=dict(empty_suffixes),embedded_NUL_rejected=True,representation='Raw streams retained once with exact offset/byte/hash index; no full JSON stream duplication.')

def join(r):
 r.verify(['endpoint_inventory','pairs','observations','forward_align','reverse_align','scope','variant_census','old_census','head_helper','normalizer','lookup_key_dependency','dictionary_en','dictionary_es','direct_relations','apertium_protocol'])
 annotation=R/'annotation-r01';ar=json.loads((annotation/'receipt.json').read_text());assert ar['complete'] and ar['protocol_sha256']==r.receipt['protocol_sha256']
 for name,b in ar['outputs'].items():assert sha(annotation/name)==b['sha256'],name
 idx=dbread(annotation/'index.sqlite');raw={s:(annotation/(s+'.raw')).open('rb') for s in ('morph','tag')};helper=load('retained_heads',r.path('head_helper'));dbs={'source':dbread(r.path('dictionary_en')),'target':dbread(r.path('dictionary_es'))};identities={s:helper._database_identity(db) for s,db in dbs.items()};tagmap=json.loads(r.path('apertium_protocol').read_text())['tag_to_UPOS'];scope=json.loads(r.path('scope').read_text());vc=json.loads(r.path('variant_census').read_text());prior=json.loads(r.path('old_census').read_text());direct=json.loads(r.path('direct_relations').read_text())['relations'];assert len(direct)==17
 heads=scope['new_head_ids'];bykey=collections.defaultdict(list)
 for h in heads:bykey[h['source_key']].append(h)
 variants={v['id']:dict(v,source_key=k) for k,c in vc.items() for v in c['variants']};seen=collections.Counter();oldsets=collections.defaultdict(lambda:collections.defaultdict(lambda:collections.defaultdict(set)));metrics=collections.defaultdict(lambda:collections.defaultdict(set));role_counts=collections.Counter();obs_count=0;joins=0;relation_count=0;db=sqlite3.connect(r.out/'evidence.sqlite');db.execute('PRAGMA page_size=4096');db.execute('PRAGMA max_page_count=23040');db.execute('PRAGMA cache_size=-8192');db.execute('CREATE TABLE objects(id TEXT PRIMARY KEY,kind TEXT,data TEXT) WITHOUT ROWID');db.execute('CREATE TABLE relations(head TEXT,observation TEXT,stratum TEXT,object_id TEXT,PRIMARY KEY(head,observation,stratum,object_id)) WITHOUT ROWID');object_seen=set();logical=0;writes=0
 def remember(kind,value):
  nonlocal logical,writes
  text=enc(value);ident=hashlib.sha256(enc([kind,value]).encode()).hexdigest()
  if ident not in object_seen:
   prospective=len(text.encode())+len(ident)+len(kind);assert logical+prospective<92*MiB,'prospective logical proof quota, no alternatives dropped';logical+=prospective;db.execute('INSERT INTO objects VALUES(?,?,?)',(ident,kind,text));object_seen.add(ident);writes+=1
   if writes%500==0:db.commit();r.check()
  return ident
 def read_roles(e):
  k=endpoint_key(e);row=idx.execute('SELECT * FROM endpoints WHERE key=?',(k,)).fetchone();assert row is not None and row['text_sha']==hashlib.sha256(e['text'].encode()).hexdigest();assert row['geometry_sha']==hashlib.sha256(json.dumps(e['tokens'],sort_keys=True).encode()).hexdigest();mapped={}
  for stage in ('morph','tag'):
   raw[stage].seek(row[stage+'_offset']);b=raw[stage].read(row[stage+'_bytes']);assert hashlib.sha256(b).hexdigest()==row[stage+'_sha'];mapped[stage]=stream.map_units(b.decode(),e['text'])
  units=[]
  for u in mapped['tag']:
   if not u['codepoints']:continue
   morphology=[v for v in mapped['morph'] if v['codepoints']==u['codepoints']];value={'endpoint_key':k,'utf16':u['utf16'],'codepoints':u['codepoints'],'contextual_readings':u['readings'],'morphological_readings':[v['readings'] for v in morphology],'stream_index_reference':{'tag_offset':row['tag_offset'],'tag_bytes':row['tag_bytes'],'morph_offset':row['morph_offset'],'morph_bytes':row['morph_bytes']}};ident=remember('lexical_unit',value);roles=[stream.reading_role(x,tagmap) for x in u['readings']];units.append({'utf16':u['utf16'],'evidence_id':ident,'chosen_roles':roles,'unknown':any(x in ('UNKNOWN','UNMAPPED_TAG') for x in roles),'joined_morphemes':'UNASSESSABLE_JOINED_MORPHEMES' in roles})
  return units
 def unit_ref(e,u):return remember('dictionary_unit',{'endpoint_key':endpoint_key(e),'unit':{k:v for k,v in u.items() if k!='forms'},'form_evidence_refs':[remember('dictionary_form',f) for f in u['forms']]})
 def role(e,u,f,lu,envelope):
  val=form_role_evidence(u,f,e,lu,envelope);val['endpoint_key']=endpoint_key(e);return val
 def add_metric(stratum,phase,h,p,a,b,identity):
  m=metrics[(stratum,phase)];m['heads'].add(h['id']);m['pairs'].add(p['pair_id']);m['components'].add(p['source']['component']);m['source_occurrences'].add(enc([p['source']['id'],p['source']['fingerprint'],p['source']['record_sha256'],a,b]));m['alternatives'].add(enc([h['id'],identity]))
 def parse_links(line,p):
  links={tuple(map(int,x.split('-'))) for x in line.split()};assert all(0<=a<len(p['source']['tokens']) and 0<=b<len(p['target']['tokens']) for a,b in links);return links
 try:
  with gzip.open(r.path('observations'),'rt') as ob,gzip.open(r.path('pairs'),'rt') as ps,r.path('forward_align').open() as fs,r.path('reverse_align').open() as rs:
   pending=next(ob,None);pending=json.loads(pending) if pending else None;pair_count=0
   for line,fl,rl in zip(ps,fs,rs,strict=True):
    p=json.loads(line);assert p['index']==pair_count;pair_count+=1;selected=[]
    while pending is not None and pending['pair_index']==p['index']:
     if pending['variant_id'] in variants:selected.append(pending)
     nxt=next(ob,None);pending=json.loads(nxt) if nxt else None
    assert pending is None or pending['pair_index']>p['index']
    if not selected:continue
    for side in ('source','target'):geometry(p[side])
    forward=parse_links(fl,p);reverse=parse_links(rl,p);union=forward|reverse;mutual=forward&reverse;allunits={s:helper._dictionary_units(dbs[s],p[s]['text'],helper._tokens(p[s]['text'],p[s]['tokens']),identities[s]) for s in ('source','target')};lus={s:read_roles(p[s]) for s in ('source','target')}
    for o in selected:
     v=variants[o['variant_id']];assert o['pair_id']==p['pair_id'] and o['component']==p['source']['component']==p['target']['component'];ss,se=o['source_tokens'];ts,te=o['target_tokens'];assert 0<=ss<se<=len(p['source']['tokens']) and 0<=ts<te<=len(p['target']['tokens']);seen[o['variant_id']]+=1;obs_count+=1
     for side,span,label in [('source',(ss,se),'source_key'),('target',(ts,te),'target_key')]:
      tok=p[side]['tokens'];text=p[side]['text'][tok[span[0]]['codepoints'][0]:tok[span[1]-1]['codepoints'][1]];assert norm(text)==v[label]
     for h in bykey[v['source_key']]:
      joins+=1;a,b=[ss+x for x in h['relative_focus_tokens']];assert ss<=a<b<=se;targets=sorted({t for s,t in union if a<=s<b});envelope_reasons=[];source_units=[u for u in allunits['source'] if u['scope']['tokens']==[a,b]];target_units=[];ta=tb=None
      if not targets:envelope_reasons.append('no_union_aligned_target')
      else:
       ta,tb=targets[0],targets[-1]+1
       if targets!=list(range(ta,tb)):envelope_reasons.append('noncontiguous_union_target')
       if not ts<=ta<tb<=te:envelope_reasons.append('aligned_focus_outside_variant_target')
       if not any(a<=s<b and ta<=t<tb for s,t in mutual):envelope_reasons.append('no_mutual_focus_anchor')
       if any((a<=s<b)!=(ta<=t<tb) for s,t in union):envelope_reasons.append('union_crosses_focus')
       if tb-ta>5:envelope_reasons.append('target_span_exceeds_dictionary_unit_bound')
       else:target_units=[u for u in allunits['target'] if ta<=u['scope']['tokens'][0]<u['scope']['tokens'][1]<=tb]
      observation=hashlib.sha256(enc([h['id'],o]).encode()).hexdigest();senv=[p['source']['tokens'][a]['utf16'][0],p['source']['tokens'][b-1]['utf16'][1]];tenv=None if ta is None else [p['target']['tokens'][ta]['utf16'][0],p['target']['tokens'][tb-1]['utf16'][1]]
      remember('observation',{'id':observation,'head':h['id'],'variant':o['variant_id'],'pair_id':p['pair_id'],'pair_index':p['index'],'component':o['component'],'source_endpoint_key':endpoint_key(p['source']),'target_endpoint_key':endpoint_key(p['target']),'source_focus_tokens':[a,b],'target_aligned_tokens':targets,'original_envelope_reasons':envelope_reasons,'source_units':[unit_ref(p['source'],u) for u in source_units],'target_units':[unit_ref(p['target'],u) for u in target_units]});done_direct=set()
      for su in source_units:
       smasks=helper._maskers(su,allunits['source']);smaskrefs=[remember('mask',{'endpoint_key':endpoint_key(p['source']),'mask':helper._mask(u)}) for u in allunits['source'] if u['unit_id'] in smasks]
       for sf in su['forms']:
        if not sf['complete'] or sf['mode'] not in (1,2) or sf['pos']!='noun':continue
        sr=role(p['source'],su,sf,lus['source'],senv);source_reasons=set(sf['reasons']);g=su['guard'];name_exception=bool(g and g['reason']=='name' and g['blocked'] and not g['target_blocked'])
        if name_exception:source_reasons.discard('dictionary_guard')
        for tu in target_units:
         ua,ub=tu['scope']['tokens'];tmasks=helper._maskers(tu,allunits['target']);tmaskrefs=[remember('mask',{'endpoint_key':endpoint_key(p['target']),'mask':helper._mask(u)}) for u in allunits['target'] if u['unit_id'] in tmasks];focus_reasons=[]
         if not any(a<=s<b and ua<=t<ub for s,t in mutual):focus_reasons.append('no_mutual_anchor')
         if any((a<=s<b)!=(ua<=t<ub) for s,t in union):focus_reasons.append('union_edge_crosses_exact_form')
         if smasks:focus_reasons.append('inside_larger_source_unit')
         if tmasks:focus_reasons.append('inside_larger_target_unit')
         for tf in tu['forms']:
          if not tf['complete'] or tf['mode'] not in (1,2) or tf['pos']!='noun':continue
          tr=role(p['target'],tu,tf,lus['target'],tenv);both=sr['role']=='NOUN' and tr['role']=='NOUN';form_supported=not source_reasons and not tf['reasons'] and sf['number']==tf['number'];base={'head':h['id'],'observation_id':observation,'pair_id':p['pair_id'],'component':o['component'],'source_unit_ref':unit_ref(p['source'],su),'target_unit_ref':unit_ref(p['target'],tu),'source_form_ref':remember('dictionary_form',sf),'target_form_ref':remember('dictionary_form',tf),'source_role':sr,'target_role':tr,'source_name_exception_inherited':name_exception,'original_envelope_reasons':envelope_reasons,'exact_focus_reasons':focus_reasons,'source_masks':smaskrefs,'target_masks':tmaskrefs,'number_agrees':sf['number']==tf['number'],'target_inside_larger_envelope':tu['scope']['tokens']!=[ta,tb]}
          for st in sf['terms']:
           for tt in tf['terms']:
            if st['sense_id']!=tt['sense_id']:continue
            stratum='old_explicit_shared_link' if st['explicit'] and tt['explicit'] else 'old_nonexplicit_shared_link';eligible=form_supported and st['eligible'] and tt['eligible'] and not st['reasons'] and not tt['reasons'];identity=[tf['lexeme_id'],tf['form_id'],tu['scope']['text'],tt['reading']];value=dict(base,stratum=stratum,source_term=st,target_term=tt,original_form_number_term_eligible=eligible,both_exact_form_roles_noun=both);rid=remember('relation',value);db.execute('INSERT OR IGNORE INTO relations VALUES(?,?,?,?)',(h['id'],observation,stratum,rid));relation_count+=1;add_metric(stratum,'all_retained_relations',h,p,a,b,identity)
            if eligible:add_metric(stratum,'form_number_term_eligible',h,p,a,b,identity)
            if eligible and both:add_metric(stratum,'eligible_forms_and_both_roles_noun',h,p,a,b,identity)
            if eligible and both and not focus_reasons and not envelope_reasons:add_metric(stratum,'eligible_forms_roles_alignment_masks_clear',h,p,a,b,identity)
            if stratum=='old_explicit_shared_link' and eligible and not envelope_reasons and tu['scope']['tokens']==[ta,tb]:
             old=oldsets[h['id']][enc(identity)];old['pair_ids'].add(p['pair_id']);old['components'].add(o['component']);old['source_occurrences'].add(enc([p['source']['id'],p['source']['fingerprint'],p['source']['record_sha256'],a,b]));old['paired_occurrences'].add(enc([p['pair_id'],a,b]));add_metric(stratum,'legacy_envelope_before_roles',h,p,a,b,identity)
             if both:add_metric(stratum,'legacy_envelope_after_roles',h,p,a,b,identity)
          for relation in direct:
           if relation['target_language']!='es' or relation['target_native_entry_id']!=tf['lexeme_id'] or relation['source_pos']!='noun' or helper.lookup_key(relation['published_source_spelling'],'en')!=su['key']:continue
           di=(su['unit_id'],tf['form_id'],relation['relation_id'])
           if di in done_direct:continue
           done_direct.add(di);sourceforms=[f for f in su['forms'] if f['complete'] and f['mode'] in (1,2) and f['pos']=='noun'];value={k:v for k,v in base.items() if k not in ('source_form_ref','source_role','number_agrees','source_name_exception_inherited')};value.update(stratum='new_direct_english_unresolved_candidate',candidate_relation=relation,source_occurrence_role={k:sr[k] for k in ('unit_id','actual_form_utf16','actual_occurrence_text','aligned_envelope_utf16','role_status','role','raw_analysis_refs','endpoint_key','reason')},source_form_evidence=[{'form_ref':remember('dictionary_form',f),'role_evidence':role(p['source'],su,f,lus['source'],senv),'number_agrees':f['number']==tf['number'],'original_reasons':f['reasons'],'source_name_exception_inherited':name_exception} for f in sourceforms],source_entry_resolved=False,source_sense_id=None,both_exact_form_roles_noun=both);rid=remember('relation',value);db.execute('INSERT OR IGNORE INTO relations VALUES(?,?,?,?)',(h['id'],observation,value['stratum'],rid));relation_count+=1;identity=[tf['lexeme_id'],tf['form_id'],tu['scope']['text'],'unresolved-direct:'+relation['relation_id']];add_metric(value['stratum'],'all_retained_relations',h,p,a,b,identity)
           if both:add_metric(value['stratum'],'both_roles_noun_identity_still_unresolved',h,p,a,b,identity)
      r.progress(observations=obs_count,head_joins=joins,relations=relation_count,logical_proof_bytes=logical)
    db.commit();r.check()
   assert pair_count==40000 and pending is None
  assert obs_count==12485 and joins==12500;assert dict(seen)=={k:v['observations'] for k,v in variants.items()}
  # Exact legacy availability parity before crediting new role or focused-form evidence.
  for h in heads:
   expected=prior['heads'][h['id']]['alternatives'];actual=oldsets[h['id']];assert set(actual)==set(expected),('legacy alternative identities',h['id'])
   for ident,sets in actual.items():
    for name,values in sets.items():
     bound=expected[ident][name];assert len(values)==bound['count'] and hashlib.sha256(enc(sorted(values)).encode()).hexdigest()==bound['sorted_identity_sha256'],('legacy independent identity parity',h['id'],name)
  summary={'heads':len(heads),'observations':obs_count,'head_observation_joins':joins,'relation_rows':db.execute('SELECT COUNT(*) FROM relations').fetchone()[0],'objects':len(object_seen),'logical_proof_bytes':logical,'legacy_alternative_and_independent_identity_parity':True,'metrics':[{'stratum':k[0],'phase':k[1],**{name:{'count':len(values),'sorted_identity_sha256':hashlib.sha256(enc(sorted(values)).encode()).hexdigest()} for name,values in metric.items()}} for k,metric in sorted(metrics.items())],'limits':'Availability only; overlapping relation strata, unresolved identities and old reasons retained; role matches are not semantic approval. New exact form-span evidence does not mutate old eligibility or selector.'};(r.out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');r.receipt.update(summary={k:v for k,v in summary.items() if k!='metrics'})
 finally:
  db.commit();db.close();idx.close();helper.clear_unit_cache()
  for f in raw.values():f.close()
  for d in dbs.values():d.close()

def main():
 assert sys.argv[1] in ('annotate','join');r=Run(sys.argv[1])
 try:
  {'annotate':annotate,'join':join}[sys.argv[1]](r);r.finish()
 except BaseException as e:r.finish(repr(e));raise
if __name__=='__main__':main()
