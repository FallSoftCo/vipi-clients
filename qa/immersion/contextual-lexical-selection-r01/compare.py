"""Frozen surrogate lexical-choice experiment. No runtime/catalog mutations."""
import collections,functools,gzip,hashlib,json,math,os,re,resource,shutil,signal,socket,sqlite3,sys,time,unicodedata
from pathlib import Path
R=Path('/srv/fallsoft/staging/vipi-contextual-lexical-selection-20261109-r01')
MiB=1024**2

def enc(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(x):return hashlib.sha256(enc(x).encode()).hexdigest()
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(MiB),b''):h.update(b)
 return h.hexdigest()
def norm(s):return ' '.join(unicodedata.normalize('NFC',s).casefold().split())
def endpoint(e):return hashlib.sha256(json.dumps([e['language'],e['id'],e['text'],e['tokens']],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
def ro(p):
 d=sqlite3.connect(Path(p).as_uri()+'?mode=ro&immutable=1',uri=True);d.execute('PRAGMA query_only=ON');d.execute('PRAGMA cache_size=-8192');return d
class Run:
 def __init__(self,stage):
  assert socket.gethostname()=='fallsoft-production-20261106';self.start=time.monotonic();self.p=json.loads((R/'protocol.json').read_text());assert sha(__file__)==self.p['code_sha256'];self.out=R/stage;self.out.mkdir(exist_ok=False);self.receipt={'complete':False,'stage':stage,'protocol_sha256':sha(R/'protocol.json')};os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});os.nice(10);resource.setrlimit(resource.RLIMIT_AS,(1024**3,)*2);signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('300s ceiling')));signal.alarm(300);assert shutil.disk_usage(R).free>8*1024**3+192*MiB
 def verify(self):
  for name,v in self.p['inputs'].items():assert sha(v['path'])==v['sha256'],name
 def write(self,name,value):
  b=(json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode();assert sum(p.stat().st_size for p in R.rglob('*') if p.is_file())+len(b)<128*MiB,'aggregate output quota; retain failure';(self.out/name).write_bytes(b)
 def finish(self,error=None):
  self.receipt.update(complete=error is None,error=error,seconds=time.monotonic()-self.start,VmHWM_bytes=int(next(x.split()[1] for x in Path('/proc/self/status').read_text().splitlines() if x.startswith('VmHWM:')))*1024,outputs={p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in self.out.iterdir() if p.is_file()});self.write('receipt.json',self.receipt);print(enc(self.receipt),flush=True)

def features(e,span,units):
 tok=e['tokens'];indices=[i for i,t in enumerate(tok) if t['utf16']==span];assert len(indices)==1;focus=indices[0];lemma={}
 for u in units:
  reads=u['contextual_readings']
  if len(reads)==1 and not reads[0].startswith('*') and '+' not in reads[0] and '<' in reads[0]:lemma[tuple(u['utf16'])]=norm(reads[0].split('<')[0])
 local=set();sentence=set()
 for i,t in enumerate(tok):
  if i==focus or not any(c.isalpha() for c in t['text']):continue
  vals=['t:'+norm(t['text'])];l=lemma.get(tuple(t['utf16']))
  if l:vals.append('l:'+l)
  sentence.update(vals)
  if 0<abs(i-focus)<=2:local.update(str(i-focus)+':'+v for v in vals)
 return {'local':sorted(local),'sentence':sorted(sentence)},focus

def prepare(r):
 r.verify();db=ro(r.p['inputs']['evidence']['path']);rej=collections.Counter();groups={};forms={};needed=set();raw_counts=collections.Counter()
 @functools.lru_cache(maxsize=20000)
 def obj(ref):
  row=db.execute('SELECT data FROM objects WHERE id=?',(ref,)).fetchone();assert row;return json.loads(row[0])
 for rid,raw in db.execute("SELECT id,data FROM objects WHERE kind='relation'"):
  d=json.loads(raw);pool={'old_explicit_shared_link':'explicit','new_direct_english_unresolved_candidate':'direct'}.get(d['stratum']);raw_counts[d['stratum']]+=1
  if pool is None:continue
  sr=d.get('source_role',d.get('source_occurrence_role'));tr=d['target_role'];reasons=[]
  if not d['both_exact_form_roles_noun']:reasons.append('actual_roles')
  if d['original_envelope_reasons']:reasons.append('alignment_envelope')
  if d['exact_focus_reasons']:reasons.append('alignment_or_compound_masks')
  if not sr['actual_occurrence_text'].islower():reasons.append('source_not_lowercase')
  tf=obj(d['target_form_ref']);forms[d['target_form_ref']]=tf
  if pool=='explicit':
   if not d['original_form_number_term_eligible']:reasons.append('original_form_number_term_guards')
   sourceforms=[(d['source_form_ref'],obj(d['source_form_ref']))]
  else:
   assert d['source_entry_resolved'] is False and d['source_sense_id'] is None
   sourceforms=[]
   for z in d['source_form_evidence']:
    sf=obj(z['form_ref']);remaining=set(z['original_reasons'])
    if z['source_name_exception_inherited']:remaining.discard('dictionary_guard')
    if sf['complete'] and sf['mode'] in (1,2) and sf['pos']=='noun' and not remaining and z['number_agrees']:sourceforms.append((z['form_ref'],sf))
   if not sourceforms or not tf['complete'] or tf['mode'] not in (1,2) or tf['pos']!='noun' or tf['reasons']:reasons.append('direct_form_number_guards')
  if reasons:
   rej.update(pool+':'+x for x in reasons);continue
  # Preserve separate number keys if the dictionary admits alternative forms; no first-form choice.
  for sfref,sf in sourceforms:
   assert sf['number']==tf['number'];key=enc([norm(sr['actual_occurrence_text']),'noun',sf['number']]);occ=digest([pool,sr['endpoint_key'],sr['actual_form_utf16'],key]);face=tr['actual_occurrence_text'];g=groups.setdefault(occ,{'id':occ,'pool':pool,'key':key,'endpoint':sr['endpoint_key'],'span':sr['actual_form_utf16'],'component':d['component'],'pair_ids':set(),'targets':{},'source_form_refs':set()});assert g['component']==d['component'];g['pair_ids'].add(d['pair_id']);g['source_form_refs'].add(sfref);forms[sfref]=sf
   t=g['targets'].setdefault(face,{'relation_refs':set(),'target_form_refs':set(),'pair_ids':set()});t['relation_refs'].add(rid);t['target_form_refs'].add(d['target_form_ref']);t['pair_ids'].add(d['pair_id']);needed.add(d['pair_id'])
 exposures=json.loads(Path(r.p['inputs']['exposures']['path']).read_text());hashes=set(exposures['hashes']);components=set(exposures.get('components',[]));endpoints={};pairs={};all_components=collections.defaultdict(set);component_pairs=collections.Counter();component_sources=collections.defaultdict(set)
 with gzip.open(r.p['inputs']['pairs']['path'],'rt') as f:
  for line in f:
   p=json.loads(line);component_pairs[p['source']['component']]+=1;component_sources[p['source']['component']].add(endpoint(p['source']))
   for side in ('source','target'):
    e=p[side];all_components[endpoint(e)].add(e['component'])
    if any(hashlib.sha256(s.encode()).hexdigest() in hashes for s in (e['text'],norm(e['text']))):components.add(e['component'])
   if p['pair_id'] in needed:
    pairs[p['pair_id']]=p
    for side in ('source','target'):endpoints[endpoint(p[side])]=p[side]
 assert set(pairs)==needed;assert all(len(v)==1 for v in all_components.values())
 units=collections.defaultdict(list)
 for _,raw in db.execute("SELECT id,data FROM objects WHERE kind='lexical_unit'"):
  u=json.loads(raw)
  if u['endpoint_key'] in endpoints:units[u['endpoint_key']].append(u)
 rows=[]
 for g in sorted(groups.values(),key=lambda x:x['id']):
  e=endpoints[g['endpoint']];assert e['component']==g['component'];matches=[t for t in e['tokens'] if t['utf16']==g['span']]
  if len(matches)!=1:rej[g['pool']+':source_not_single_native_token']+=1;continue
  a,b=matches[0]['codepoints'];assert norm(e['text'][a:b])==json.loads(g['key'])[0];g['features'],g['focus_index']=features(e,g['span'],units[g['endpoint']]);g['source_identity']=[e['id'],e['fingerprint'],e['record_sha256'],g['span']];g['split']='development' if g['component'] in components else 'test' if int(digest(['contextual-lexical-selection-r01',g['component']])[:16],16)%5==0 else 'train';g['pair_ids']=sorted(g['pair_ids']);g['source_form_refs']=sorted(g['source_form_refs']);g['targets']={face:{k:sorted(v) for k,v in x.items()} for face,x in sorted(g['targets'].items())};rows.append(g)
 traincomp={x['component'] for x in rows if x['split']=='train'};testcomp={x['component'] for x in rows if x['split']=='test'};devcomp={x['component'] for x in rows if x['split']=='development'};assert not traincomp&testcomp and not traincomp&devcomp and not testcomp&devcomp
 split={'rows':[{k:x[k] for k in ('id','pool','key','source_identity','component','split')} for x in rows],'exposed_components':sorted(components),'train_components':sorted(traincomp),'test_components':sorted(testcomp),'development_components':sorted(devcomp),'no_component_overlap':True,'protocol_sha256':sha(R/'protocol.json')};r.write('split-freeze.json',split);r.write('dataset.json',{'rows':rows,'pairs':pairs,'endpoints':endpoints,'dictionary_forms':forms,'source_evidence_sha256':r.p['inputs']['evidence']['sha256']});r.write('availability.json',{'raw_relation_rows':dict(raw_counts),'overlapping_rejections':dict(rej),'rows':len(rows),'counts':{pool:{split:sum(x['pool']==pool and x['split']==split for x in rows) for split in ('train','test','development')} for pool in ('explicit','direct')},'component1':{'all40k_pairs':component_pairs[1],'all40k_source_endpoints':len(component_sources[1]),'eligible_occurrences':sum(x['component']==1 for x in rows),'quarantined':1 in components},'split_sha256':sha(r.out/'split-freeze.json')});db.close()

def fit(rows,kind):
 # Each component has total mass 1 per source-key. Conflicting faces split occurrence mass.
 sizes=collections.Counter(x['component'] for x in rows);vocab=set();docs=collections.defaultdict(set)
 for x in rows:
  for f in x['features'].get(kind,[]):docs[f].add(x['component'])
 vocab={f for f,c in docs.items() if len(c)>=2};prior=collections.Counter();counts=collections.defaultdict(collections.Counter)
 for x in rows:
  weight=1/(sizes[x['component']]*len(x['targets']))
  for target in x['targets']:
   prior[target]+=weight
   for f in x['features'].get(kind,[]):
    if f in vocab:counts[target][f]+=weight
 return prior,counts,vocab

def predict(model,features,kind):
 prior,counts,vocab=model
 if not prior:return None,{}
 total=sum(prior.values());n=len(prior);scores={}
 for t in sorted(prior):
  score=math.log((prior[t]+1)/(total+n))
  if kind!='default' and vocab:
   denominator=sum(counts[t].values())+len(vocab)
   score+=sum(math.log((counts[t][f]+1)/denominator) for f in features if f in vocab)
  scores[t]=score
 return min(scores,key=lambda t:(-scores[t],-prior[t],t)),scores

def controls():
 # Duplicating translations/forms is removed by set-valued occurrence data, not extra votes.
 rows=[{'component':1,'targets':{'a':{},'b':{}},'features':{'local':['x']}} for _ in range(3)]
 m=fit(rows,'local');assert abs(sum(m[0].values())-1)<1e-12 and m[0]['a']==m[0]['b'];assert predict(m,[],'default')[0]=='a';assert predict(({}, {},set()),[],'local')[0] is None
 # Unseen context cannot change frequency fallback.
 rows=[{'component':i,'targets':{'a' if i<3 else 'b':{}},'features':{'local':['x']}} for i in range(4)];m=fit(rows,'local');assert predict(m,['unseen'],'local')[0]==predict(m,[],'default')[0]
 return True

def compare(r):
 controls();pr=json.loads((R/'prepare/receipt.json').read_text());assert pr['complete'] and pr['protocol_sha256']==sha(R/'protocol.json')
 for n,b in pr['outputs'].items():assert sha(R/'prepare'/n)==b['sha256']
 data=json.loads((R/'prepare/dataset.json').read_text());rows=data['rows'];train=collections.defaultdict(list)
 for x in rows:
  if x['split']=='train':train[(x['pool'],x['key'])].append(x)
 models={k:{kind:fit(v,kind) for kind in ('default','local','sentence')} for k,v in train.items()};preds=[];metrics={};training=[]
 for k,v in train.items():training.append({'pool':k[0],'key':k[1],'occurrences':len(v),'components':len({x['component'] for x in v}),'targets':sorted({t for x in v for t in x['targets']}),'conflict_occurrences':sum(len(x['targets'])>1 for x in v),'feature_vocab':{kind:len(models[k][kind][2]) for kind in ('local','sentence')}})
 for x in rows:
  if x['split']=='train':continue
  m=models.get((x['pool'],x['key']));out={'id':x['id'],'pool':x['pool'],'split':x['split'],'component':x['component'],'key':x['key'],'observed_faces':sorted(x['targets']),'conflicting_observed_faces':len(x['targets'])>1,'train_occurrences':len(train[(x['pool'],x['key'])]),'train_components':len({v['component'] for v in train[(x['pool'],x['key'])]}),'train_faces':sorted(m['default'][0]) if m else [],'methods':{}}
  for kind in ('default','local','sentence'):
   target,scores=predict(m[kind],x['features'].get(kind,[]),kind) if m else (None,{});out['methods'][kind]={'target':target,'scores':scores,'agrees_with_any_observed_face':target in x['targets'] if target is not None else False,'zero_immersion':target is not None and norm(target)==json.loads(x['key'])[0]}
  out['unsupported_observed_faces']=sorted(set(x['targets'])-set(out['train_faces']));preds.append(out)
 for pool in ('explicit','direct'):
  for split in ('test','development'):
   xs=[x for x in preds if x['pool']==pool and x['split']==split];key=pool+':'+split;summary={'occurrences':len(xs),'components':len({x['component'] for x in xs}),'source_keys':len({x['key'] for x in xs}),'no_training_key':sum(not x['train_faces'] for x in xs),'all_observed_faces_unseen':sum(not set(x['observed_faces'])&set(x['train_faces']) for x in xs),'any_unseen_observed_face':sum(bool(x['unsupported_observed_faces']) for x in xs),'conflicting_reference_faces':sum(x['conflicting_observed_faces'] for x in xs),'single_train_face':sum(len(x['train_faces'])==1 for x in xs),'multiple_train_faces':sum(len(x['train_faces'])>1 for x in xs),'less_than_three_train_components':sum(x['train_components']<3 for x in xs),'methods':{}}
   for kind in ('default','local','sentence'):
    supported=[x for x in xs if x['train_faces']];amb=[x for x in supported if len(x['train_faces'])>1];summary['methods'][kind]={'predicted':len(supported),'agreement_any_reference':sum(x['methods'][kind]['agrees_with_any_observed_face'] for x in xs),'agreement_single_target_pool':sum(x['methods'][kind]['agrees_with_any_observed_face'] for x in supported if len(x['train_faces'])==1),'single_target_denominator':sum(len(x['train_faces'])==1 for x in supported),'agreement_ambiguous_train_pool':sum(x['methods'][kind]['agrees_with_any_observed_face'] for x in amb),'ambiguous_denominator':len(amb),'changed_from_default':sum(x['methods'][kind]['target']!=x['methods']['default']['target'] for x in xs),'surrogate_gain':sum(x['methods'][kind]['agrees_with_any_observed_face'] and not x['methods']['default']['agrees_with_any_observed_face'] for x in xs),'surrogate_loss':sum(not x['methods'][kind]['agrees_with_any_observed_face'] and x['methods']['default']['agrees_with_any_observed_face'] for x in xs),'zero_immersion':sum(x['methods'][kind]['zero_immersion'] for x in xs)}
   metrics[key]=summary
 r.write('predictions.json',preds);r.write('training-support.json',training);r.write('metrics.json',metrics)
 # Frozen quotas, hash order, one source/component; no outcome-based backfill.
 byid={x['id']:x for x in rows};strata={'changed':[],'same_ambiguous':[],'single_target':[]};used=set();selected=[]
 for p in preds:
  if p['split']!='test' or p['pool']!='explicit' or not p['train_faces']:continue
  changed=len({z['target'] for z in p['methods'].values()})>1;stratum='changed' if changed else 'same_ambiguous' if len(p['train_faces'])>1 else 'single_target';strata[stratum].append(p)
 for s,quota in [('changed',8),('same_ambiguous',4),('single_target',4)]:
  n=0
  for p in sorted(strata[s],key=lambda x:digest(['blind-review-r01',x['id']])):
   if p['component'] in used:continue
   selected.append((s,p));used.add(p['component']);n+=1
   if n==quota:break
 packet=[];key=[]
 for i,(s,p) in enumerate(selected,1):
  x=byid[p['id']];e=data['endpoints'][x['endpoint']];t=e['tokens'][x['focus_index']];a,b=t['codepoints'];alternatives=sorted({z['target'] for z in p['methods'].values() if z['target'] is not None},key=lambda target:digest(['blind-option-r01',x['id'],target]));options=[{'option_id':chr(65+j),'target':target,'mixed_output':e['text'][:a]+target+e['text'][b:]} for j,target in enumerate(alternatives)];caseid='lexical-'+str(i).zfill(3)
  support=[v for v in train[(x['pool'],x['key'])]];pairids=set(x['pair_ids'])|{pid for v in support for pid in v['pair_ids']};packet.append({'case_id':caseid,'stable_source_focus_id':x['id'],'source':e,'focus_utf16':x['span'],'options':options,'all_train_competing_faces':p['train_faces'],'full_parallel_witnesses':{pid:data['pairs'][pid] for pid in sorted(pairids)},'support_occurrences':[{k:v[k] for k in ('id','component','source_identity','targets','pair_ids')} for v in support],'test_observation':{k:x[k] for k in ('targets','pair_ids','component')},'interpretation':'One frozen focus substituted into complete corpus source sentence, not native chat budget projection. Parallel target agreement is surrogate; review full mixed sentence.'});key.append({'case_id':caseid,'stratum':s,'prediction_id':p['id'],'method_options':{kind:next(o['option_id'] for o in options if o['target']==z['target']) for kind,z in p['methods'].items()}})
 r.write('review-selection-freeze.json',{'quota':{'changed':8,'same_ambiguous':4,'single_target':4},'eligible':{k:len(v) for k,v in strata.items()},'selected':[{'id':p['id'],'stratum':s,'component':p['component']} for s,p in selected],'no_backfill':True,'split_sha256':sha(R/'prepare/split-freeze.json')});r.write('blind-review-packet.json',{'cases':packet,'method_labels_present':False,'prior_chat_available':False,'scope':'Corpus full-sentence lexical-focus diagnostic only; component held out and prior exposure quarantined.'});r.write('review-method-key.json',key);r.receipt['mechanism_controls_passed']=True

def main():
 r=Run(sys.argv[1])
 try:{'prepare':prepare,'compare':compare}[sys.argv[1]](r);r.finish()
 except BaseException as e:r.finish(repr(e));raise
if __name__=='__main__':main()
