#!/usr/bin/env python3
"""Read-only accounting of frozen context evidence and recorded decisions.
No extraction, inference, selector replay, guard changes, or proof copying.
"""
import collections,gzip,hashlib,itertools,json,os,resource,shutil,signal,socket,sqlite3,time,unicodedata,zlib
from pathlib import Path
ROOT=Path('/srv/fallsoft/staging/vipi-context-key-expansion-20261109-r01')
HERE=Path(__file__).resolve().parent
FILES={'heads':('outputs/heads-r02/heads.sqlite','df310b8628079900c2e2ee5c638a21de6e1ef1cc9b15c1a20ae7479a83bcfd90'),'decisions':('outputs/project-r02/decisions.jsonl.gz','255d89336001a080f7cb3e188246da4c81fad3c8f5874cc9195f4f7c6f4cdaaf'),'keys':('inputs/matched-keys.json.gz','74df5e859e3ea1c221c751521ffb3501e84e9301044e7457277de19f8b2ac19f'),'geometry':('inputs/rows.jsonl','fc41c289c79d3d7d07a72b5f9041c359565f88cdca38deaf5cc0569530425780'),'annotations':('inputs/annotations.jsonl','d74ad01af3d62c969993a96f2c10d51ad6a25986af2e5b8cbf8e9711c61776fe'),'protocol':('code/qa/immersion/context-key-expansion-r01/head-protocol-r02.json','51739ac6a8d9f44ea385fd7ecb025c866bb3f5d7f440c35f6dd5dc0cafaa25b8'),'metrics':('outputs/project-r02/metrics.json','10a5384aee0371b24eebc6c99ed0c06b606dd03995116363e5af4d537233850b')}
STAGES=['source_context','aligned_context','shared_head_context','eligible_link_context','structural_head_context','projected_candidate','single_token','role_assessed','role_compatible','content_classified','nonidentical','literal_allowed','compound_allowed','known_allowed','pre_budget','selected']
HEAD_ORDER=['no_eligible_shared_sense_pos_number','no_mutual_anchor','union_edge_crosses_focus','inside_larger_source_unit','inside_larger_target_unit','competing_target_geometry']
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def norm(s):return ' '.join(unicodedata.normalize('NFC',s).casefold().split())
def write(p,x):
 data=(json.dumps(x,ensure_ascii=False,indent=2)+'\n').encode();assert len(data)<4*1024**2
 assert sum(x.stat().st_size for x in p.parent.iterdir() if x.is_file())+len(data)<=5*1024**2
 with p.open('xb') as f:f.write(data)
def main():
 assert socket.gethostname()=='fallsoft-production-20261106' and ROOT.resolve()==ROOT
 start=time.monotonic();os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});os.nice(10);resource.setrlimit(resource.RLIMIT_AS,(1024**3,)*2)
 def timeout(*unused):raise TimeoutError('120s accounting ceiling')
 signal.signal(signal.SIGALRM,timeout);signal.alarm(120)
 assert shutil.disk_usage(ROOT).free>=8*1024**3+5*1024**2
 out=ROOT/'outputs/loss-accounting-r01';out.mkdir(exist_ok=False);receipt={'complete':False,'production':False,'script_sha256':sha(Path(__file__))};db=None
 try:
  for name,(rel,digest) in FILES.items():assert sha(ROOT/rel)==digest,name
  receipt['inputs']={k:{'path':str(ROOT/v[0]),'sha256':v[1]} for k,v in FILES.items()}
  keys={x['source_key']:x for x in json.load(gzip.open(ROOT/FILES['keys'][0],'rt'))};assert len(keys)==25931
  db=sqlite3.connect((ROOT/FILES['heads'][0]).as_uri()+'?mode=ro&immutable=1',uri=True);db.execute('PRAGMA query_only=ON');db.execute('PRAGMA cache_size=-8192')
  sql={'contexts':db.execute('SELECT count(*),count(DISTINCT source_key) FROM contexts').fetchone(),'eligible_heads':db.execute('SELECT count(*),count(DISTINCT source_key) FROM heads').fetchone()}
  phase={k:{'source_context'} for k in keys};head_overlap=collections.Counter();head_exclusive=collections.Counter();link_overlap=collections.Counter();unit_overlap=collections.Counter();empty_context_detail=collections.Counter();totals=collections.Counter();key_terminal=collections.Counter()
  for key,fixed,blob in db.execute('SELECT source_key,fixed,proof FROM contexts ORDER BY id'):
   assert key in keys and bool(fixed)==keys[key]['fixed'];result=json.loads(zlib.decompress(blob))['result'];hs=result['heads'];state=phase[key];state.add('aligned_context');totals['contexts']+=1
   if hs:state.add('shared_head_context')
   if any(any(m['structural_eligible'] for m in h['shared_senses']) for h in hs):state.add('eligible_link_context')
   if any(h['structural_eligible'] for h in hs):state.add('structural_head_context')
   for h in hs:
    totals['candidate_heads']+=1;head_overlap.update(h['reasons'])
    terminal=next((x for x in HEAD_ORDER if x in h['reasons']),'eligible');assert (terminal=='eligible')==h['structural_eligible'];head_exclusive[terminal]+=1
    for m in h['shared_senses']:
     totals['shared_link_records']+=1;totals['eligible_link_records']+=m['structural_eligible'];link_overlap.update(m['reasons'])
   for rejected in result['rejected']:
    if rejected['kind']=='unit':
     totals[rejected['side']+'_rejected_unit_records']+=1
     unit_overlap.update(rejected['side']+':'+reason for reason in rejected['reasons'])
   if not hs:
    supported={}
    for side in ['source','target']:
     forms=[f for u in result['rejected'] if u['kind']=='unit' and u['side']==side for f in u['unit']['forms']]
     supported[side]=any(f['complete'] and f['mode'] in [1,2] and f['pos'] in ['noun','adj','adv'] for f in forms)
    bucket='no_complete_supported_source_form' if not supported['source'] else 'no_complete_supported_target_form' if not supported['target'] else 'both_supported_no_shared_link'
    empty_context_detail[bucket]+=1
  assert totals['contexts']==19960 and totals['candidate_heads']==21425 and head_exclusive['eligible']==2556
  for key,state in phase.items():
   terminal=next(('no_'+s for s in STAGES[1:5] if s not in state),'structural_head_context');key_terminal[terminal]+=1
  assert sum(key_terminal.values())==25931
  msg=collections.defaultdict(collections.Counter);candidates=collections.defaultdict(collections.Counter);focus=collections.defaultdict(collections.Counter);exclusive=collections.defaultdict(collections.Counter);prefilter=collections.defaultdict(collections.Counter);selector_overlap=collections.defaultdict(collections.Counter);geometry_reject=collections.Counter();native=collections.Counter();first20=[];rows=0
  with gzip.open(ROOT/FILES['decisions'][0],'rt') as decisions,(ROOT/FILES['geometry'][0]).open() as geometry,(ROOT/FILES['annotations'][0]).open() as anns:
   for raw,graw in zip(decisions,geometry,strict=True):
    row,g,a=json.loads(raw),json.loads(graw),json.loads(next(anns));assert row['id']==g['id']==a['id'] and row['text']==g['text'] and a['pass']==0
    assert a['source_sha256']==hashlib.sha256(row['text'].encode()).hexdigest()
    if rows<20:first20.append((a['id'],a['source_sha256'],a['tokens']))
    rows+=1;cs=row['candidates'];words=row['native_words_utf16'];rawtext=row['text'].encode('utf-16-le');native['native_word_occurrences']+=len(words)
    roles={(x,y):tag for x,y,tag,_ in a['tokens']};role_words={tuple(x) for x in words if roles.get(tuple(x)) in ['NOUN','ADJ','ADV']};native['exact_native_words_tagged_noun_adj_adv']+=len(role_words)
    native['exact_native_words_tagged_verb_aux_out_of_scope']+=sum(roles.get(tuple(x)) in ['VERB','AUX'] for x in words)
    window_states={arm:set() for arm in ['fixed','expanded']};context_covered=set()
    for left,right in g['native_window_ranges_utf16']:
     key=norm(rawtext[2*left:2*right].decode('utf-16-le'))
     if key not in phase:continue
     window_states['expanded']|=phase[key]
     if keys[key]['fixed']:window_states['fixed']|=phase[key]
     context_covered.update(x for x in role_words if left<=x[0]<x[1]<=right)
    native['role_words_inside_any_retained_source_context']+=len(context_covered)
    native['role_words_outside_all_retained_source_contexts']+=len(role_words-context_covered)
    native['role_words_with_any_projected_focus']+=len(role_words & {tuple(c['focus_utf16']) for c in cs})
    geometry_reject.update(x['reason'] for x in row['geometry_rejections'])
    for arm in ['fixed','expanded']:
     arm_cs=[i for i,c in enumerate(cs) if arm=='expanded' or c['fixed']]
     for i in arm_cs:prefilter[arm].update(cs[i]['filter_reasons'])
     for known,decisions in row['decisions'].items():
      label=arm+'|'+known;decision=decisions[arm];reject={x['index']:set(x['reasons']) for x in decision['rejected']};stages={s:s in window_states[arm] for s in STAGES[:5]};indices=arm_cs[:]
      def record(stage):
       stages[stage]=bool(indices);candidates[label][stage]+=len(indices);focus[label][stage]+=len({tuple(cs[i]['focus_utf16']) for i in indices})
      record('projected_candidate')
      for stage,reason in [('single_token','not_single_token_head'),('role_assessed','role_unassessed'),('role_compatible','role_conflict'),('content_classified','not_content_classified')]:
       indices=[i for i in indices if reason not in cs[i]['filter_reasons']];record(stage)
      assert set(indices)=={i for i in arm_cs if not cs[i]['filter_reasons']}
      for stage,predicate in [('nonidentical',lambda i:not cs[i]['identical_face']),('literal_allowed',lambda i:'protected_focus' not in reject.get(i,set())),('compound_allowed',lambda i:'inside_recognized_source_unit' not in reject.get(i,set())),('known_allowed',lambda i:not reject.get(i,set())&{'known_function','known_vocabulary'})]:
       indices=[i for i in indices if predicate(i)];record(stage)
      indices=decision['pre_budget_indices'];record('pre_budget');indices=decision['selected_indices'];record('selected')
      for x in decision['rejected']:selector_overlap[label].update(x['reasons'])
      prior=True
      for stage in STAGES:
       assert not stages[stage] or prior,(row['id'],label,stage,'non-nested message stage')
       msg[label][stage]+=stages[stage];prior=stages[stage]
      exclusive[label][next(('no_'+s for s in STAGES if not stages[s]),'selected')]+=1
    if rows%2000==0:print(json.dumps({'stage':'decisions_accounting','rows':rows,'seconds':time.monotonic()-start}),flush=True)
   repeats=[json.loads(x) for x in anns];assert len(repeats)==20
   assert [(x['id'],x['source_sha256'],x['tokens']) for x in repeats]==first20 and all(x['pass']==1 for x in repeats)
  assert rows==9535 and all(sum(c.values())==9535 for c in exclusive.values())
  expected=json.loads((ROOT/FILES['metrics'][0]).read_text())
  for label,c in msg.items():assert c['selected']==expected[label]['nonempty'] and candidates[label]['selected']==expected[label]['changed_words']
  result={'production':False,'source_keys':{'matched':len(keys),'aligned':19960,'stage_presence':{s:sum(s in v for v in phase.values()) for s in STAGES[:5]},'exclusive_terminal':dict(key_terminal)},'database_counts':sql,'proof_counts':dict(totals),'head_reason_overlap':dict(head_overlap),'head_exclusive_terminal':dict(head_exclusive),'head_exclusive_order':HEAD_ORDER,'shared_link_reason_overlap':dict(link_overlap),'unit_reason_overlap':dict(unit_overlap),'contexts_without_any_shared_head':dict(empty_context_detail),'messages_stage_presence':dict(msg),'messages_exclusive_first_loss':dict(exclusive),'candidate_instances_stage_presence':dict(candidates),'distinct_focus_occurrences_stage_presence':dict(focus),'candidate_prefilter_reason_overlap':dict(prefilter),'selector_reason_overlap':dict(selector_overlap),'geometry_rejection_records':dict(geometry_reject),'native_occurrence_scope':dict(native),'exclusive_stage_order':STAGES,'caveats':['Shared dictionary links are retained pivot senses, not exhaustive source meanings; nonexplicit direct-English links can be valid but are excluded by this historical helper.','Reason counts overlap and use different denominators: links, heads, contexts, candidate instances, distinct message-local focuses, messages. Never add them as a loss total.','Message first-loss attribution depends on the declared ordering; stages are availability of at least one survivor, not percentages of correct vocabulary.','Early source/aligned/head-context coverage refers to matching context keys; it is not evidence that each content word inside that context has a valid translated focus.','Source absence means no retained eligible source window under this inventory/tokenization; single-word cap and stop/geometry policies are confounded with corpus absence.','Actual noun/adj/adv token tags are diagnostic potential-content scope, not semantic truth; verbs remain deliberately excluded.','No guard was relaxed or selector rerun. Existing top target/representative restrictions remain.']}
  write(out/'result.json',result);receipt['complete']=True
 except BaseException as e:receipt['error']=repr(e);raise
 finally:
  if db is not None:db.close()
  receipt.update(seconds=time.monotonic()-start,memory={k:int(v.split()[0])*1024 for k,v in (x.split(':',1) for x in Path('/proc/self/status').read_text().splitlines() if x.startswith(('VmHWM:','VmPeak:')))},outputs={p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in out.iterdir() if p.is_file()});write(out/'receipt.json',receipt);print(json.dumps(receipt),flush=True)
if __name__=='__main__':main()
