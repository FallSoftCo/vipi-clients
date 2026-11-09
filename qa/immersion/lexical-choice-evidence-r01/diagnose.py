#!/usr/bin/env python3
"""Read-only lexical evidence census; never chooses or emits a translation."""
import argparse,collections,contextlib,gzip,hashlib,importlib.util,json,os,resource,shutil,signal,socket,sqlite3,time,zlib
from pathlib import Path
ROOT=Path('/srv/fallsoft/staging/vipi-lexical-choice-evidence-20261109-r01');HERE=ROOT/'code';MiB=1024**2

def enc(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(MiB),b''):h.update(b)
 return h.hexdigest()
def load(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
class Run:
 def __init__(self,stage):
  assert socket.gethostname()=='fallsoft-production-20261106' and Path(__file__).resolve()==HERE/'diagnose.py'
  self.started=time.monotonic();self.stage=stage;self.stack=contextlib.ExitStack();self.plan=json.loads((HERE/'protocol.json').read_text());self.paths={k:Path(v['path']) for k,v in self.plan['inputs'].items()};self.out=ROOT/'outputs'/stage
  os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});os.nice(10);resource.setrlimit(resource.RLIMIT_AS,(1024**3,)*2)
  def timeout(*args):raise TimeoutError('120s diagnosis limit')
  signal.signal(signal.SIGALRM,timeout);signal.alarm(120);assert shutil.disk_usage(ROOT).free>=8*1024**3+8*MiB;self.out.mkdir(parents=True,exist_ok=False);self.receipt={'complete':False,'stage':stage,'protocol_sha256':sha(HERE/'protocol.json'),'production':False}
 def verify(self):
  assert sha(__file__)==self.plan['script_sha256']
  for k,b in self.plan['inputs'].items():assert self.paths[k].resolve()==self.paths[k] and sha(self.paths[k])==b['sha256'],k
  self.adapter=load('frozen_adapter',self.paths['adapter']);self.h=self.adapter.helpers(self)
 def db(self,key):
  db=sqlite3.connect(self.paths[key].as_uri()+'?mode=ro&immutable=1',uri=True);db.row_factory=sqlite3.Row;db.execute('PRAGMA query_only=ON');db.execute('PRAGMA cache_size=-8192');self.stack.callback(db.close);return db
 def write(self,name,x):
  b=(enc(x)+'\n').encode();assert sum(p.stat().st_size for p in (ROOT/'outputs').rglob('*') if p.is_file())+len(b)<8*MiB-(0 if name=='receipt.json' else 65536),'metadata quota; no alternatives dropped'
  with (self.out/name).open('xb') as f:f.write(b)
 def prior(self):
  p=ROOT/'outputs/metadata';receipt=json.loads((p/'receipt.json').read_text());assert receipt['complete'] and receipt['protocol_sha256']==self.receipt['protocol_sha256']
  for name,b in receipt['outputs'].items():assert sha(p/name)==b['sha256']
  return p
 def finish(self,error=None):
  self.stack.close();self.receipt.update(complete=error is None,error=error,seconds=time.monotonic()-self.started,memory={k:int(v.split()[0])*1024 for k,v in (s.split(':',1) for s in Path('/proc/self/status').read_text().splitlines() if s.startswith(('VmHWM:','VmPeak:')))},outputs={p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in self.out.iterdir() if p.is_file()});self.write('receipt.json',self.receipt);print(enc(self.receipt),flush=True)

def metadata(r):
 cat=r.db('catalog');variants=r.db('variants');frozen=[];keys={};joins=0
 for row in cat.execute('SELECT id,source_key,record,audit FROM heads WHERE baseline=0 AND experimental=1 ORDER BY id'):
  record=json.loads(row['record']);audit=json.loads(row['audit']);assert audit['override_links'] and not audit['baseline']
  frozen.append({'id':row['id'],'source_key':row['source_key'],'relative_focus_tokens':record['source_focus_relative_tokens'],'record_sha256':hashlib.sha256(row['record'].encode()).hexdigest(),'audit_sha256':hashlib.sha256(row['audit'].encode()).hexdigest(),'original_context_id':record['context_id'],'original_head_id':record['head_id']})
  key=row['source_key']
  if key not in keys:
   vs=[dict(x) for x in variants.execute('SELECT id,target_key,observations,distinct_components,example_pair_index,source_start,source_end,target_start,target_end FROM ranked WHERE source_key=? ORDER BY id',(key,))];assert vs
   keys[key]={'variants':vs,'wholephrase_distinct_targets':len({v['target_key'] for v in vs}),'observation_count':sum(v['observations'] for v in vs)}
  joins+=keys[key]['observation_count']
 assert len(frozen)==1480
 packet=json.loads(r.paths['packet'].read_text());added=[]
 for c in packet['cases']:
  for i,u in enumerate(c['review_union']):
   if u['arms']==['experimental']:
    added.append({'review_id':c['review_id'],'source_id':c['source_id'],'known':c['known'],'union_index':i,'source':u['source'],'target':u['target'],'focus_utf16':u['focus_utf16'],'candidate_head_ids':[c['candidates'][j]['head_id'] for j in u['candidate_indices']],'source_sha256':hashlib.sha256(c['source'].encode()).hexdigest()})
 assert len(added)==29 and added==json.loads(r.paths['audit_freeze'].read_text())['added_emissions'] and all(set(x['candidate_head_ids'])<={h['id'] for h in frozen} for x in added)
 r.write('scope-freeze.json',{'new_head_ids':frozen,'added_sampled_emissions':added,'packet_sha256':sha(r.paths['packet']),'before_occurrence_evidence':True})
 r.write('variant-census.json',keys)
 r.write('preflight.json',{'new_heads':1480,'source_keys':len(keys),'retained_variant_rows':sum(len(x['variants']) for x in keys.values()),'wholephrase_multi_target_keys':sum(x['wholephrase_distinct_targets']>1 for x in keys.values()),'head_observation_join_upper_bound':joins,'unique_observation_upper_bound':sum(x['observation_count'] for x in keys.values()),'next_stage_requires_root_review':True,'interpretation':'Wholephrase target diversity is not noun-choice diversity. Inspect this measured metadata size/count before authorizing occurrence pass; no partial key sampling or silent truncation.'})
 r.receipt.update(heads=len(frozen),source_keys=len(keys),head_observation_join_upper_bound=joins)

def verify_observation(pair,o,variant,norm):
 assert o['pair_index']==pair['index'] and o['pair_id']==pair['pair_id']
 assert o['component']==pair['source']['component']==pair['target']['component']
 for side,key in [('source','source_key'),('target','target_key')]:
  data=pair[side];a,b=o[side+'_tokens'];tokens=data['tokens']
  assert isinstance(a,int) and isinstance(b,int) and 0<=a<b<=len(tokens)
  text=data['text'][tokens[a]['codepoints'][0]:tokens[b-1]['codepoints'][1]]
  assert norm(text)==variant[key],(side,'variant spelling mismatch')
  assert o[side+'_codepoints']==[tokens[a]['codepoints'][0],tokens[b-1]['codepoints'][1]]
  assert o[side+'_utf16']==[tokens[a]['utf16'][0],tokens[b-1]['utf16'][1]]

def occurrences(r):
 prior=r.prior();approval=json.loads((ROOT/'inputs/occurrence-approval.json').read_text());assert approval['authorized'] and approval['protocol_sha256']==r.receipt['protocol_sha256'] and approval['metadata_receipt_sha256']==sha(prior/'receipt.json')
 scope=json.loads((prior/'scope-freeze.json').read_text());census=json.loads((prior/'variant-census.json').read_text());heads=scope['new_head_ids'];bykey=collections.defaultdict(list)
 for h in heads:bykey[h['source_key']].append(h)
 variant_metadata={v['id']:dict(v,source_key=k) for k,c in census.items() for v in c['variants']};variant_keys={i:v['source_key'] for i,v in variant_metadata.items()};variant_seen=collections.Counter();assert len(variant_keys)==sum(len(c['variants']) for c in census.values())
 helper=load('frozen_dictionary_units',r.paths['head_helper']);en=r.db('dictionary_en');es=r.db('dictionary_es');r.stack.callback(helper.clear_unit_cache);identities={'source':helper._database_identity(en),'target':helper._database_identity(es)}
 audit_ids={h for a in scope['added_sampled_emissions'] for h in a['candidate_head_ids']};aggregates={h['id']:{'observations':0,'independent_pairs':set(),'independent_components':set(),'independent_source_occurrences':set(),'reject_overlap':collections.Counter(),'alternatives':{}} for h in heads};details=[];pair_evidence={};unit_evidence={};form_evidence={};link_evidence={};obs_seen=0
 def units(pair,side,start,end):
  data=pair[side];tokens=data['tokens'][start:end];db=en if side=='source' else es
  found=helper._dictionary_units(db,data['text'],helper._tokens(data['text'],tokens),identities[side]);cp=[tokens[0]['codepoints'][0],tokens[-1]['codepoints'][1]]
  return [u for u in found if u['scope']['codepoints']==cp]
 def remember_unit(u,language):
  compact={k:v for k,v in u.items() if k!='forms'};compact['form_refs']=[]
  for form in u['forms']:
   fid=hashlib.sha256(enc([language,form]).encode()).hexdigest();form_evidence.setdefault(fid,{'language':language,'form':form});compact['form_refs'].append(fid)
  identity=hashlib.sha256(enc([language,compact]).encode()).hexdigest();unit_evidence.setdefault(identity,{'language':language,'unit':compact});return identity
 def process(pair,forward,reverse,o):
  nonlocal obs_seen
  key=variant_keys.get(o['variant_id'])
  if key is None:return
  verify_observation(pair,o,variant_metadata[o['variant_id']],r.h.norm);variant_seen[o['variant_id']]+=1
  obs_seen+=1;ss,se=o['source_tokens'];st=pair['source']['tokens'];tt=pair['target']['tokens'];assert r.h.norm(pair['source']['text'][st[ss]['codepoints'][0]:st[se-1]['codepoints'][1]])==key
  union=forward|reverse;mutual=forward&reverse
  for h in bykey[key]:
   agg=aggregates[h['id']];agg['observations']+=1;agg['independent_pairs'].add(pair['pair_id']);agg['independent_components'].add(o['component']);a,b=[ss+x for x in h['relative_focus_tokens']];assert ss<=a<b<=se
   source_occurrence_key=enc([pair['source']['id'],pair['source']['fingerprint'],pair['source']['record_sha256'],a,b]);agg['independent_source_occurrences'].add(source_occurrence_key)
   targets=sorted({t for s,t in union if a<=s<b});reasons=[];source_units=units(pair,'source',a,b);target_units=[];supported=[]
   if not targets:reasons.append('no_union_aligned_target')
   else:
    ta,tb=targets[0],targets[-1]+1
    if targets!=list(range(ta,tb)):reasons.append('noncontiguous_union_target')
    if not o['target_tokens'][0]<=ta<tb<=o['target_tokens'][1]:reasons.append('aligned_focus_outside_variant_target')
    if not any(a<=s<b and ta<=t<tb for s,t in mutual):reasons.append('no_mutual_focus_anchor')
    if any((a<=s<b)!=(ta<=t<tb) for s,t in union):reasons.append('union_crosses_focus')
    # At most five tokens is the unchanged dictionary unit recognition boundary.
    if tb-ta>5:reasons.append('target_span_exceeds_dictionary_unit_bound')
    else:target_units=units(pair,'target',ta,tb)
   for su in source_units:
    for sf in su['forms']:
     source_remaining=set(sf['reasons']);g=su['guard']
     if g and g['reason']=='name' and g['blocked'] and not g['target_blocked']:source_remaining.discard('dictionary_guard')
     if source_remaining or sf['pos']!='noun' or not sf['complete'] or sf['mode'] not in [1,2]:continue
     for tu in target_units:
      for tf in tu['forms']:
       if tf['reasons'] or tf['pos']!='noun' or not tf['complete'] or tf['mode'] not in [1,2] or sf['number']!=tf['number']:continue
       for sm in sf['terms']:
        for tm in tf['terms']:
         if sm['sense_id']!=tm['sense_id'] or sm['reasons'] or tm['reasons'] or not all(m['eligible'] and m['explicit'] for m in [sm,tm]):continue
         link={'source_lexeme_id':sf['lexeme_id'],'target_lexeme_id':tf['lexeme_id'],'target_surface':tf['surface'],'target_emitted_occurrence':tu['scope']['text'],'source_form_id':sf['form_id'],'target_form_id':tf['form_id'],'source_term_id':sm['term_id'],'target_term_id':tm['term_id'],'retained_linked_sense_id':sm['sense_id'],'source_sense_label':sm['label'],'source_sense_pos':sm['sense_pos'],'source_sense_url':sm['source_url'],'target_reading':tm['reading'],'number':tf['number']};supported.append(link)
   if not source_units:reasons.append('no_source_dictionary_unit')
   if targets and not target_units:reasons.append('no_target_dictionary_unit_in_bound')
   if not supported:reasons.append('no_supported_explicit_noun_pair_link')
   agg['reject_overlap'].update(set(reasons))
   if not reasons:
    # Identity/form and emitted spelling are distinct. No winner or fine-grained sense prediction.
    seen=set()
    for link in supported:
     identity=enc([link['target_lexeme_id'],link['target_form_id'],link['target_emitted_occurrence'],link['target_reading']])
     alt=agg['alternatives'].setdefault(identity,{'identity':json.loads(identity),'pair_ids':set(),'components':set(),'variant_ids':set(),'linked_sense_ids':set(),'source_occurrences':set(),'paired_occurrences':set(),'source_features':collections.Counter()})
     alt['pair_ids'].add(pair['pair_id']);alt['components'].add(o['component']);alt['variant_ids'].add(o['variant_id']);alt['linked_sense_ids'].add(link['retained_linked_sense_id'])
     paired_key=enc([pair['pair_id'],a,b]);alt['paired_occurrences'].add(paired_key);new_occurrence=source_occurrence_key not in alt['source_occurrences'];alt['source_occurrences'].add(source_occurrence_key)
     if identity not in seen and new_occurrence:
      for offset in [-2,-1,1,2]:
       index=a+offset if offset<0 else b-1+offset
       if 0<=index<len(st):alt['source_features'][enc([offset,r.h.norm(st[index]['text'])])]+=1
      seen.add(identity)
   if h['id'] in audit_ids:
    pair_evidence.setdefault(pair['pair_id'],{'pair_index':pair['index'],'component':o['component'],'source':pair['source'],'target':pair['target'],'forward_links':sorted(forward),'reverse_links':sorted(reverse),'provenance':pair['provenance']})
    refs=[]
    for link in supported:
     lid=hashlib.sha256(enc(link).encode()).hexdigest();link_evidence.setdefault(lid,link);refs.append(lid)
    details.append({'head_id':h['id'],'variant_id':o['variant_id'],'pair_id':pair['pair_id'],'source_tokens':[a,b],'aligned_target_tokens':targets,'source_units':[remember_unit(u,'en') for u in source_units],'target_units':[remember_unit(u,'es') for u in target_units],'overlapping_reasons':sorted(set(reasons)),'all_supported_link_refs':refs,'dictionary_support_is_not_candidate_eligibility':'Whole-sentence compound/literal/source-role controls are not rerun; this is evidence availability only.','occurrence_POS_and_sense_annotation':'No corpus occurrence POS/sense annotation retained; dictionary linked senses only. Native review role is separately present in original packet.'})
 with gzip.open(r.paths['observations'],'rt') as observations,gzip.open(r.paths['pairs'],'rt') as pairs,r.paths['forward_align'].open() as fs,r.paths['reverse_align'].open() as rs:
  pending=next(observations,None);pending=json.loads(pending) if pending else None;pair_count=0
  for raw,fline,rline in zip(pairs,fs,rs,strict=True):
   pair=json.loads(raw);assert pair['index']==pair_count;pair_count+=1
   forward=r.h.parse_links(fline,len(pair['source']['tokens']),len(pair['target']['tokens']));reverse=r.h.parse_links(rline,len(pair['source']['tokens']),len(pair['target']['tokens']))
   while pending is not None and pending['pair_index']==pair['index']:
    process(pair,forward,reverse,pending);rawobs=next(observations,None);pending=json.loads(rawobs) if rawobs else None
   assert pending is None or pending['pair_index']>pair['index']
  assert pair_count==40000 and pending is None
 assert obs_seen==sum(x['observation_count'] for x in census.values())
 assert dict(variant_seen)=={i:v['observations'] for i,v in variant_metadata.items()},'per-variant observation count mismatch'
 def plain(x):
  if isinstance(x,set):return sorted(x)
  if isinstance(x,dict):return {k:({'count':len(v),'sorted_identity_sha256':hashlib.sha256(enc(sorted(v)).encode()).hexdigest()} if k in ['pair_ids','components','source_occurrences','paired_occurrences','independent_source_occurrences','independent_pairs','independent_components'] and isinstance(v,set) else plain(v)) for k,v in x.items()}
  if isinstance(x,list):return [plain(v) for v in x]
  return x
 summary={'heads':len(heads),'heads_with_supported_alternative':sum(bool(a['alternatives']) for a in aggregates.values()),'heads_with_multiple_target_lexemes':sum(len({v['identity'][0] for v in a['alternatives'].values()})>1 for a in aggregates.values()),'heads_with_multiple_emitted_faces':sum(len({v['identity'][2] for v in a['alternatives'].values()})>1 for a in aggregates.values()),'heads_with_two_target_lexemes_each_two_components':sum(len({v['identity'][0] for v in a['alternatives'].values() if len(v['components'])>=2})>=2 for a in aggregates.values()),'observations':obs_seen,'no_correctness_or_training_label_claim':True}
 r.write('census.json',{'summary':summary,'heads':plain(aggregates),'limits':r.plan['interpretation']});r.write('audit-evidence.json',{'all29_added_emissions':scope['added_sampled_emissions'],'occurrences':details,'full_pairs':pair_evidence,'dictionary_units':unit_evidence,'dictionary_forms':form_evidence,'supported_links':link_evidence,'limits':r.plan['interpretation']})
 # Title-span evidence is independent of target-choice diversity and uses existing masks only.
 packet=json.loads(r.paths['packet'].read_text());title=next(c for c in packet['cases'] if c['review_id']=='name-scope-011');geometry=None
 with r.paths['geometry'].open() as f:
  for line in f:
   g=json.loads(line)
   if g['id']==title['source_id']:geometry=g;break
 assert geometry and geometry['text']==title['source'];inventory={x['source_key']:x for x in json.load(gzip.open(r.paths['matched_keys'],'rt'))};raw=title['source'].encode('utf-16-le');span=r.plan['name_diagnostic']['title_utf16'];assert raw[2*span[0]:2*span[1]].decode('utf-16-le')=='dragon ball z'
 windows=[{'utf16':[a,b],'source_key':r.h.norm(raw[2*a:2*b].decode('utf-16-le')),'retained_source_context_present':r.h.norm(raw[2*a:2*b].decode('utf-16-le')) in inventory} for a,b in geometry['native_window_ranges_utf16'] if a<span[1] and b>span[0]]
 r.write('name-span-inventory.json',{'source_id':title['source_id'],'source':title['source'],'title_utf16':span,'native_words_utf16':title['native_words_utf16'],'existing_source_masks':title['source_masks'],'existing_protected_ranges_utf16':title['protected_ranges_utf16'],'existing_candidates':title['candidates'],'all_intersecting_native_context_windows':windows,'no_new_entity_detector_or_protection_rule':True})
 r.receipt['summary']=summary

def main():
 ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['metadata','occurrences']);args=ap.parse_args();r=Run(args.stage)
 try:r.verify();globals()[args.stage](r);r.finish()
 except BaseException as e:r.finish(repr(e));raise
if __name__=='__main__':main()
