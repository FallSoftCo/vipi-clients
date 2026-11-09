"""Frozen contiguous-context lookup with longest-match frequency backoff."""
import collections,hashlib,json,math,os,re,resource,shutil,signal,socket,sqlite3,sys,time,unicodedata
from pathlib import Path
R=Path('/srv/fallsoft/staging/vipi-context-rule-lookup-20261109-r01');N=Path('/srv/fallsoft/staging/vipi-contextual-lexical-selection-20261109-r01');C=Path('/srv/fallsoft/staging/vipi-apertium-corpus-evidence-20261109-r01');MiB=1024**2

def enc(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(x):return hashlib.sha256(enc(x).encode()).hexdigest()
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(MiB),b''):h.update(b)
 return h.hexdigest()
def norm(t):return ' '.join(unicodedata.normalize('NFC',t).casefold().split())
def rss():return int(next(x.split()[1] for x in Path('/proc/self/status').read_text().splitlines() if x.startswith('VmRSS:')))*1024
def graph_bytes(x,seen=None):
 if seen is None:seen=set()
 if id(x) in seen:return 0
 seen.add(id(x));n=sys.getsizeof(x)
 if isinstance(x,dict):n+=sum(graph_bytes(k,seen)+graph_bytes(v,seen) for k,v in x.items())
 elif isinstance(x,(list,tuple,set)):n+=sum(graph_bytes(v,seen) for v in x)
 return n
class Run:
 def __init__(self,stage):
  assert socket.gethostname()=='fallsoft-production-20261106';self.start=time.monotonic();self.p=json.loads((R/'protocol.json').read_text());assert sha(__file__)==self.p['code_sha256'];self.out=R/stage;self.out.mkdir(exist_ok=False);self.receipt={'complete':False,'stage':stage,'protocol_sha256':sha(R/'protocol.json')};os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});os.nice(10);resource.setrlimit(resource.RLIMIT_AS,(1024**3,)*2);signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('300s bound')));signal.alarm(300);assert shutil.disk_usage(R).free>8*1024**3+192*MiB
 def verify(self):
  for k,v in self.p['inputs'].items():assert sha(v['path'])==v['sha256'],k
 def write(self,name,value,compact=False):
  b=((enc(value) if compact else json.dumps(value,ensure_ascii=False,indent=2))+'\n').encode();assert sum(p.stat().st_size for p in R.rglob('*') if p.is_file())+len(b)<96*MiB,'output bound; no truncation';(self.out/name).write_bytes(b)
 def finish(self,error=None):
  self.receipt.update(complete=error is None,error=error,seconds=time.monotonic()-self.start,VmHWM_bytes=int(next(x.split()[1] for x in Path('/proc/self/status').read_text().splitlines() if x.startswith('VmHWM:')))*1024,outputs={p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in self.out.iterdir() if p.is_file()});self.write('receipt.json',self.receipt);print(enc({k:v for k,v in self.receipt.items() if k!='outputs'}),flush=True)

def context_inventory(data):
 endpoints={x['endpoint'] for x in data['rows'] if x['pool']=='explicit'};lemma=collections.defaultdict(dict);db=sqlite3.connect((C/'join-r02/evidence.sqlite').as_uri()+'?mode=ro&immutable=1',uri=True);db.execute('PRAGMA query_only=ON');db.execute('PRAGMA cache_size=-8192')
 for raw, in db.execute("SELECT data FROM objects WHERE kind='lexical_unit'"):
  u=json.loads(raw);reads=u['contextual_readings']
  if u['endpoint_key'] not in endpoints or len(reads)!=1:continue
  a=reads[0];tags=re.findall(r'<([^>]+)>',a)
  if a.startswith('*') or '+' in a or '#' in a or not tags:continue
  lemma[u['endpoint_key']][tuple(u['utf16'])]=norm(a.split('<')[0])+'<'+tags[0]+'>'
 db.close();out={}
 for k in sorted(endpoints):
  e=data['endpoints'][k];token=[norm(t['text']) if any(c.isalpha() for c in t['text']) else None for t in e['tokens']];lem=[lemma[k].get(tuple(t['utf16'])) if token[i] is not None else None for i,t in enumerate(e['tokens'])];out[k]={'tokens':token,'lemmas':lem,'token_geometry_sha256':digest(e['tokens']),'source_sha256':hashlib.sha256(e['text'].encode()).hexdigest()}
 return out

def windows(x,context,wide=False):
 i=x['focus_index'];out=[]
 for channel,seq in [('token',context['tokens']),('lemma_pos',context['lemmas'])]:
  for a,b in ([(a,a+n) for n in range(2,9) for a in range(i-n+1,i+1)] if wide else [(i-1,i+1),(i,i+2),(i-1,i+2)]):
   if a<0 or b>len(seq) or any(v is None for v in seq[a:b]):continue
   key=enc([x['key'],channel,i-a,seq[a:b]]);out.append({'key':key,'channel':channel,'length':b-a,'focus_offset':i-a,'values':seq[a:b],'source_tokens':[a,b]})
 return out

def default_winner(counts):return min(counts,key=lambda t:(-counts[t],t)) if counts else None

def controls():
 x={'focus_index':1,'key':'source'};c={'tokens':['a','word','b'],'lemmas':['a<det>','word<n>','b<n>']};ws=windows(x,c);assert len(ws)==6 and sorted(w['length'] for w in ws)==[2,2,2,2,3,3];c['tokens'][0]=None;assert len([w for w in windows(x,c) if w['channel']=='token'])==1;assert default_winner({'a':1,'b':1})=='a';assert default_winner({}) is None
 assert len(windows(x,{'tokens':['a','word','b'],'lemmas':[None]*3},wide=True))==3
 rr=lambda n,ch='token':{'rule':{'length':n,'channel':ch,'ratio':2,'winner_independent_components':2,'winner_weight':1,'id':'x'},'source_tokens':[0,n]}
 assert rank_match(rr(4))<rank_match(rr(3));assert rank_match(rr(3))<rank_match(rr(3,'lemma_pos'))
 assert not windows({'focus_index':0,'key':'x'},{'tokens':['only'],'lemmas':['only<n>']},wide=True)
 return True

def compile_rules(r):
 r.verify();assert controls();data=json.loads((N/'prepare/dataset.json').read_text());contexts=context_inventory(data);rows=[x for x in data['rows'] if x['pool']=='explicit' and x['split']=='train'];bykey=collections.defaultdict(list)
 component_splits=collections.defaultdict(set);text_splits=collections.defaultdict(set)
 for x in data['rows']:
  component_splits[x['component']].add(x['split']);text_splits[norm(data['endpoints'][x['endpoint']]['text'])].add(x['split'])
 assert all(len(v)==1 for v in component_splits.values());assert all(len(v)==1 for v in text_splits.values())
 assert len(rows)==2987
 for x in rows:bykey[x['key']].append(x)
 defaults={};patterns={};weights={}
 for key,xs in bykey.items():
  sizes=collections.Counter(x['component'] for x in xs);counts=collections.Counter()
  for x in xs:
   w=1/(sizes[x['component']]*len(x['targets']));weights[x['id']]=w
   for face in x['targets']:counts[face]+=w
  defaults[key]={'target':default_winner(counts),'weighted_counts':dict(counts),'training_occurrence_ids':[x['id'] for x in xs],'components':sorted(sizes)}
  if len(counts)<2:continue # No alternate target exists; retain default/support records, no context rule can win.
  for x in xs:
   for win in windows(x,contexts[x['endpoint']],wide=True):
    p=patterns.setdefault(win['key'],{'source_key':key,'channel':win['channel'],'length':win['length'],'focus_offset':win['focus_offset'],'values':win['values'],'counts':collections.Counter(),'support':collections.defaultdict(set),'components':collections.defaultdict(set),'occurrence_windows':{}});p['occurrence_windows'][x['id']]=win['source_tokens']
    for face in x['targets']:p['counts'][face]+=weights[x['id']];p['support'][face].add(x['id']);p['components'][face].add(x['component'])
 table={};census=[];rejected=collections.Counter()
 for key,p in sorted(patterns.items()):
  counts=p['counts'];winner=default_winner(counts);maximum=counts[winner];default=defaults[p['source_key']]['target'];ties=[face for face,v in counts.items() if abs(v-maximum)<=1e-12];den=counts.get(default,0.0);reasons=[]
  if len(defaults[p['source_key']]['weighted_counts'])<2:reasons.append('single_target_key')
  if len(ties)!=1:reasons.append('tied_context_winner')
  if winner==default:reasons.append('default_already_wins')
  if len(p['components'][winner])<2:reasons.append('winner_under_two_components')
  if maximum<=1.5*den+1e-12:reasons.append('ratio_not_strictly_above_1_5')
  ident=digest(key);record={'id':ident,'lookup_key':key,**{k:p[k] for k in ('source_key','channel','length','focus_offset','values')},'winner':winner,'default':default,'winner_weight':maximum,'default_context_weight':den,'ratio':maximum/den if den else None,'default_absent':den==0,'winner_independent_components':len(p['components'][winner]),'weighted_counts':dict(counts),'support_occurrence_ids':{f:sorted(ids) for f,ids in p['support'].items()},'support_components':{f:sorted(ids) for f,ids in p['components'].items()},'occurrence_windows':p['occurrence_windows'],'reasons':reasons};census.append(record)
  if reasons:rejected.update(reasons)
  else:table[key]={'id':ident,'target':winner,'length':p['length'],'channel':p['channel'],'ratio':record['ratio'],'default_absent':record['default_absent'],'winner_independent_components':record['winner_independent_components'],'winner_weight':maximum,'source_key':p['source_key'],'focus_offset':p['focus_offset'],'support_occurrence_ids':record['support_occurrence_ids']}
 # Existing frequency default is a hard identity control, not a newly fitted alternative baseline.
 old=json.loads((N/'compare/predictions.json').read_text())
 for x in old:
  if x['pool']=='explicit':assert defaults.get(x['key'],{}).get('target')==x['methods']['default']['target'],x['id']
 r.write('context-inventory.json',contexts,True);r.write('compiled-lookup.json',{'rules':table,'defaults':defaults,'protocol_sha256':sha(R/'protocol.json')},True);r.write('all-pattern-evidence.json',census,True);r.write('training-occurrence-evidence.json',{x['id']:x for x in rows},True);r.write('compile-summary.json',{'train_occurrences':len(rows),'train_keys':len(bykey),'source_patterns':len(patterns),'accepted_rules':len(table),'rules_by_length':dict(collections.Counter(x['length'] for x in table.values())),'rules_by_channel':dict(collections.Counter(x['channel'] for x in table.values())),'default_absent_rules':sum(x['default_absent'] for x in table.values()),'overlapping_rejection_reasons':dict(rejected),'frequency_default_parity':True,'no_test_target_used':True})

def rank_match(x):
 r=x['rule'];return (-r['length'],0 if r['channel']=='token' else 1,-(r['ratio'] if r['ratio'] is not None else math.inf),-r['winner_independent_components'],-r['winner_weight'],x['source_tokens'][0],r['id'])

def choose(table,x,contexts,wide):
 matches=[];tested=windows(x,contexts[x['endpoint']],wide=wide)
 for win in tested:
  rule=table['rules'].get(win['key'])
  if rule:matches.append({'rule':rule,'source_tokens':win['source_tokens']})
 matches.sort(key=rank_match);chosen=matches[0] if matches else None;default=table['defaults'].get(x['key'],{}).get('target');target=chosen['rule']['target'] if chosen else default
 if target is not None:assert target in table['defaults'][x['key']]['weighted_counts']
 return {'target':target,'matched_rules':[{'rule_id':v['rule']['id'],'source_tokens':v['source_tokens'],'target':v['rule']['target'],'length':v['rule']['length'],'channel':v['rule']['channel']} for v in matches],'chosen_rule_id':chosen['rule']['id'] if chosen else None,'chosen_context_tokens':chosen['source_tokens'] if chosen else None,'winning_length':chosen['rule']['length'] if chosen else 1 if default else 0,'tested_windows':tested,'conflicting_matched_targets':len({v['rule']['target'] for v in matches})>1,'reference_agreement':target in x['targets'] if target else False,'zero_immersion':target is None or norm(target)==json.loads(x['key'])[0]}

def apply_rules(r):
 r.verify();assert controls();cr=json.loads((R/'compile/receipt.json').read_text());assert cr['complete'] and cr['protocol_sha256']==sha(R/'protocol.json')
 for name,h in cr['outputs'].items():assert sha(R/'compile'/name)==h['sha256']
 before=rss();t=time.perf_counter();table=json.loads((R/'compile/compiled-lookup.json').read_text());loadtime=time.perf_counter()-t;after=rss();tablemem=graph_bytes(table);contexts=json.loads((R/'compile/context-inventory.json').read_text());data=json.loads((N/'prepare/dataset.json').read_text());rows=[x for x in data['rows'] if x['pool']=='explicit' and x['split']=='test'];assert len(rows)==781;pred=[];start=time.perf_counter()
 for x in rows:
  assert contexts[x['endpoint']]['token_geometry_sha256']==digest(data['endpoints'][x['endpoint']]['tokens'])
  default=table['defaults'].get(x['key'],{}).get('target')
  methods={m:choose(table,x,contexts,wide) for m,wide in [('narrow',False),('wide',True)]}
  methods['default']={'target':default,'reference_agreement':default in x['targets'] if default else False,'zero_immersion':default is None or norm(default)==json.loads(x['key'])[0]}
  pred.append({'id':x['id'],'source_key':x['key'],'component':x['component'],'endpoint':x['endpoint'],'source_span':x['span'],'source_focus_index':x['focus_index'],'methods':methods,'observed_faces':sorted(x['targets']),'train_faces':sorted(table['defaults'].get(x['key'],{}).get('weighted_counts',{}))})
 lookuptime=time.perf_counter()-start;summary={}
 for label,subset in [('all',pred),('multi_target',[x for x in pred if len(x['train_faces'])>1]),('single_target',[x for x in pred if len(x['train_faces'])==1]),('unseen_key',[x for x in pred if not x['train_faces']])]:
  summary[label]={'records':len(subset),'methods':{}}
  for m in ('default','narrow','wide'):
   summary[label]['methods'][m]={'reference_agreement':sum(x['methods'][m]['reference_agreement'] for x in subset),'unavailable':sum(x['methods'][m]['target'] is None for x in subset),'zero_immersion':sum(x['methods'][m]['zero_immersion'] for x in subset)}
   if m=='default':continue
   summary[label]['methods'][m].update(rule_matches=sum(bool(x['methods'][m]['matched_rules']) for x in subset),default_backoff=sum(not x['methods'][m]['matched_rules'] and x['methods']['default']['target'] is not None for x in subset),changed_outputs=sum(x['methods'][m]['target']!=x['methods']['default']['target'] for x in subset),gains=sum(x['methods'][m]['reference_agreement'] and not x['methods']['default']['reference_agreement'] for x in subset),losses=sum(not x['methods'][m]['reference_agreement'] and x['methods']['default']['reference_agreement'] for x in subset),conflicting_matched_rules=sum(x['methods'][m]['conflicting_matched_targets'] for x in subset),winning_lengths=dict(collections.Counter(x['methods'][m]['winning_length'] for x in subset)))
  summary[label]['wide_vs_narrow_changed']=sum(x['methods']['wide']['target']!=x['methods']['narrow']['target'] for x in subset)
 summary['table']={'serialized_bytes':(R/'compile/compiled-lookup.json').stat().st_size,'python_object_graph_bytes':tablemem,'load_seconds':loadtime,'process_RSS_before_load':before,'process_RSS_after_load':after,'lookup_all781_both_arms_seconds':lookuptime,'python_memory_not_mobile_runtime':True};r.write('predictions.json',pred,True);r.write('metrics.json',summary)
 exposure=json.loads((R/'review-exposures.json').read_text());excluded=set(exposure['components']);eligible=[x for x in pred if x['component'] not in excluded and any(v['target'] is not None for v in x['methods'].values())];changed=[x for x in eligible if len({v['target'] for v in x['methods'].values()})>1];controls_=[x for x in eligible if len({v['target'] for v in x['methods'].values()})==1];selected=[];seen=set()
 if changed:
  for label,items,quota in [('changed',changed,8),('control',controls_,4)]:
   count=0
   for x in sorted(items,key=lambda x:digest(['context-rule-review-r01',x['id']])):
    if x['component'] in seen:continue
    selected.append((label,x));seen.add(x['component']);count+=1
    if count==quota:break
 packet=[];key=[];source_byid={x['id']:x for x in rows}
 for i,(label,x) in enumerate(selected,1):
  e=data['endpoints'][x['endpoint']];a,b=e['tokens'][x['source_focus_index']]['codepoints'];choices=sorted({v['target'] for v in x['methods'].values()},key=lambda f:digest(['context-rule-options-r01',x['id'],f]));options=[{'option_id':chr(65+j),'target':f,'mixed_output':e['text'] if f is None else e['text'][:a]+f+e['text'][b:],'zero_immersion':f is None or norm(f)==norm(e['tokens'][x['source_focus_index']]['text'])} for j,f in enumerate(choices)];cid='context-rule-'+str(i).zfill(3);packet.append({'case_id':cid,'source_focus_id':x['id'],'source':e,'focus_utf16':x['source_span'],'options':options,'full_parallel_witnesses':{pid:data['pairs'][pid] for pid in source_byid[x['id']]['pair_ids']},'policy':'One exact focus substituted in complete original source. Unavailable/original is zero immersion, not correct immersion.'});key.append({'case_id':cid,'stratum':label,'prediction_id':x['id'],'methods':{m:next(o['option_id'] for o in options if o['target']==x['methods'][m]['target']) for m in ('default','narrow','wide')}})
 r.write('review-selection-freeze.json',{'eligible_changed_records':len(changed),'eligible_controls':len(controls_),'excluded_components':len(excluded),'selected':[{'id':x['id'],'stratum':label,'component':x['component']} for label,x in selected],'quotas':{'changed':8,'control':4},'controls_only_if_changed_exists':True,'no_backfill':True});r.write('blind-review-packet.json',{'cases':packet,'methods_present':False,'reused_benchmark':True,'no_population_accuracy_claim':True});r.write('review-method-key.json',key);r.receipt['table_memory_and_timing']=summary['table']

def main():
 r=Run(sys.argv[1])
 try:{'compile':compile_rules,'apply':apply_rules}[sys.argv[1]](r);r.finish()
 except BaseException as e:r.finish(repr(e));raise
if __name__=='__main__':main()
