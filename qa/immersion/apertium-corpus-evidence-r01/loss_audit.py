import collections,gzip,hashlib,json,os,resource,signal,sqlite3,time
from pathlib import Path
R=Path('/srv/fallsoft/staging/vipi-apertium-corpus-evidence-20261109-r01')
def enc(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def main():
 os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});os.nice(10);resource.setrlimit(resource.RLIMIT_AS,(1024**3,)*2);signal.alarm(120);start=time.monotonic();out=R/'loss-audit-r02';out.mkdir(exist_ok=False);path=R/'join-r02/evidence.sqlite';assert sha(path)=='03415f4547ed645a9dc5e9283ab4bfb77621e8ebb801f46f608a75b6053b01e3';db=sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True);db.execute('PRAGMA query_only=ON');db.execute('PRAGMA cache_size=-8192');units=collections.defaultdict(list)
 for ident,raw in db.execute("SELECT id,data FROM objects WHERE kind='lexical_unit'"):
  x=json.loads(raw);units[x['endpoint_key']].append((ident,x['utf16'],x['contextual_readings']))
 stages=collections.defaultdict(lambda:collections.defaultdict(set));categories=collections.defaultdict(lambda:collections.defaultdict(set));diagnostics=[];selected_pairs=set()
 def add(group,d,ident):
  sr=d['source_role'];group['form_pairs'].add(ident);group['heads'].add(d['head']);group['pairs'].add(d['pair_id']);group['components'].add(d['component']);group['source_occurrences'].add(enc([sr['endpoint_key'],sr['actual_form_utf16']]))
 def classify(role):
  if role['role'] is not None:return role['role']
  span=role['actual_form_utf16'];overlap=[u for u in units[role['endpoint_key']] if max(span[0],u[1][0])<min(span[1],u[1][1])];exact=[u for u in overlap if u[1]==span]
  if exact:
   readings=[r for u in exact for r in u[2]]
   if any(r.startswith('*') for r in readings):return 'UNKNOWN'
   if any('+' in r for r in readings):return 'JOINED_MORPHEMES'
   if len(readings)>1:return 'AMBIGUOUS_READINGS'
   return 'UNMAPPED_TAG'
  if any(u[1][0]<=span[0] and u[1][1]>=span[1] for u in overlap):return 'MULTIWORD_SPAN'
  return 'SPLIT_SPAN' if overlap else 'UNMAPPED_SPAN'
 for ident,raw in db.execute("SELECT id,data FROM objects WHERE kind='relation'"):
  d=json.loads(raw);stratum=d['stratum'];sr=d.get('source_role',d.get('source_occurrence_role'));tr=d['target_role'];source=sr['actual_occurrence_text'].casefold();target=tr['actual_occurrence_text'].casefold();diagnostic=('fall_otono_direct' if stratum=='new_direct_english_unresolved_candidate' and source=='fall' and target=='otoño' else 'order_pedido' if source=='order' and target=='pedido' else 'name_llamas' if source=='name' and target=='llamas' else None)
  if diagnostic:diagnostics.append({'diagnostic':diagnostic,'object_id':ident,'evidence':d});selected_pairs.add(d['pair_id'])
  if stratum!='old_explicit_shared_link' or not d['original_form_number_term_eligible'] or d['target_inside_larger_envelope'] or d['original_envelope_reasons']:continue
  identity=enc([d['observation_id'],d['source_form_ref'],d['target_form_ref']]);add(stages['legacy_before_roles'],d,identity);both=sr['role']==tr['role']=='NOUN'
  if both:
   add(stages['legacy_after_roles'],d,identity)
   if not d['exact_focus_reasons']:add(stages['legacy_after_roles_and_masks'],d,identity)
   else:
    add(categories['role_pass_but_alignment_or_mask_flagged'],d,identity)
    for reason in d['exact_focus_reasons']:add(categories['role_pass_flag_'+reason],d,identity)
  else:
   add(categories['role_failed_or_unassessable'],d,identity)
   for side,role in [('source',sr),('target',tr)]:
    label=classify(role)
    if label!='NOUN':add(categories[side+'_'+label],d,identity)
 plan=json.loads((R/'execution-protocol-r02.json').read_text());pairs=Path(plan['inputs']['pairs']['path']);assert sha(pairs)==plan['inputs']['pairs']['sha256'];witnesses={}
 with gzip.open(pairs,'rt') as f:
  for line in f:
   p=json.loads(line)
   if p['pair_id'] in selected_pairs:witnesses[p['pair_id']]=p
 assert set(witnesses)==selected_pairs
 proof_ids=set()
 for d in diagnostics:
  v=d['evidence'];proof_ids.update([v['source_unit_ref'],v['target_unit_ref'],v['target_form_ref']]);proof_ids.update(v.get('source_masks',[])+v.get('target_masks',[]));proof_ids.update(v['target_role']['raw_analysis_refs'])
  if 'source_role' in v:proof_ids.add(v['source_form_ref']);proof_ids.update(v['source_role']['raw_analysis_refs'])
  else:
   proof_ids.update(v['source_occurrence_role']['raw_analysis_refs']);proof_ids.update(x['form_ref'] for x in v['source_form_evidence'])
 proofs={}
 for ident in sorted(proof_ids):
  row=db.execute('SELECT kind,data FROM objects WHERE id=?',(ident,)).fetchone();assert row;proofs[ident]={'kind':row[0],'data':json.loads(row[1])}
 # Unit form arrays include references; preserve every referenced alternative, not just chosen links.
 pending=[x for v in proofs.values() if v['kind']=='dictionary_unit' for x in v['data']['form_evidence_refs'] if x not in proofs]
 for ident in pending:
  row=db.execute('SELECT kind,data FROM objects WHERE id=?',(ident,)).fetchone();assert row;proofs[ident]={'kind':row[0],'data':json.loads(row[1])}
 def compact(g):return {k:{'count':len(v),'identity_sha256':hashlib.sha256(enc(sorted(v)).encode()).hexdigest()} for k,v in g.items()}
 losses={}
 for before,after,label in [('legacy_before_roles','legacy_after_roles','role_only_losses'),('legacy_after_roles','legacy_after_roles_and_masks','additional_alignment_mask_only_losses')]:
  assert all(stages[after][k]<=values for k,values in stages[before].items());losses[label]={k:len(values-stages[after][k]) for k,values in stages[before].items()}
 summary={'input_evidence_sha256':sha(path),'stages':{k:compact(v) for k,v in stages.items()},'actual_independent_set_losses':losses,'overlapping_flag_categories':{k:compact(v) for k,v in sorted(categories.items())},'diagnostic_relation_rows':dict(collections.Counter(d['diagnostic'] for d in diagnostics)),'diagnostic_unique_pairs':{k:len({d['evidence']['pair_id'] for d in diagnostics if d['diagnostic']==k}) for k in sorted({d['diagnostic'] for d in diagnostics})},'limits':'No new inference or semantic labels. Flag categories overlap and can affect a form without removing its whole source/head when another alternative survives. Actual set losses are separately computed.'}
 outputs={'summary.json':summary,'diagnostic-proofs.json':{'all_matching_diagnostic_relations':diagnostics,'full_parallel_witnesses':witnesses,'referenced_objects':proofs,'input_database_sha256':sha(path),'no_semantic_acceptance':True}}
 for name,value in outputs.items():b=(json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode();assert sum(p.stat().st_size for p in out.iterdir() if p.is_file())+len(b)<8*1024**2;(out/name).write_bytes(b)
 receipt={'complete':True,'seconds':time.monotonic()-start,'VmHWM_bytes':int(next(s.split()[1] for s in Path('/proc/self/status').read_text().splitlines() if s.startswith('VmHWM:')))*1024,'script_sha256':sha(Path(__file__)),'outputs':{p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in out.iterdir() if p.is_file()}};db.close();(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt));print(json.dumps({'actual_losses':losses,'diagnostic_pairs':summary['diagnostic_unique_pairs'],'stages':{k:{n:v['count'] for n,v in x.items()} for k,x in summary['stages'].items()}}))
if __name__=='__main__':main()
