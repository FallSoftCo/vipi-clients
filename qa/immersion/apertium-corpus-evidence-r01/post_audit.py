import collections,hashlib,json,os,resource,signal,sqlite3,time
from pathlib import Path
R=Path('/srv/fallsoft/staging/vipi-apertium-corpus-evidence-20261109-r01')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});os.nice(10);resource.setrlimit(resource.RLIMIT_AS,(1024**3,)*2);signal.alarm(120);start=time.monotonic();receipt=json.loads((R/'join-r02/receipt.json').read_text());assert receipt['complete'];path=R/'join-r02/evidence.sqlite';assert sha(path)==receipt['outputs']['evidence.sqlite']['sha256'];old=R/'join-r01/evidence.sqlite';assert sha(old)=='3a44b59ddce5b834384f1dc29e4b0c6b2d9e279b5dd6d4fc7c5490ccb56a3261';db=sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True);db.execute('PRAGMA query_only=ON');db.execute('PRAGMA cache_size=-8192');db.execute('ATTACH DATABASE ? AS old',(old.as_uri()+'?mode=ro&immutable=1',))
containment={'old_objects':db.execute('SELECT COUNT(*) FROM old.objects').fetchone()[0],'old_relations':db.execute('SELECT COUNT(*) FROM old.relations').fetchone()[0],'missing_or_different_objects':db.execute('SELECT COUNT(*) FROM old.objects o LEFT JOIN main.objects n ON n.id=o.id WHERE n.id IS NULL OR n.kind!=o.kind OR n.data!=o.data').fetchone()[0],'missing_relations':db.execute('SELECT COUNT(*) FROM old.relations o LEFT JOIN main.relations n ON n.head=o.head AND n.observation=o.observation AND n.stratum=o.stratum AND n.object_id=o.object_id WHERE n.object_id IS NULL').fetchone()[0]};assert containment['missing_or_different_objects']==containment['missing_relations']==0
counts=collections.Counter();patterns=collections.defaultdict(set);legacy=collections.defaultdict(set);span=collections.defaultdict(set);direct=collections.defaultdict(set)
for (raw,) in db.execute("SELECT data FROM objects WHERE kind='relation'"):
 d=json.loads(raw);stratum=d['stratum'];counts[stratum]+=1;sr=d.get('source_role',d.get('source_occurrence_role'));tr=d['target_role'];srole=sr['role'] or 'UNASSESSABLE';trole=tr['role'] or 'UNASSESSABLE';ident=(d['observation_id'],d.get('source_form_ref','direct-unresolved'),d['target_form_ref']);patterns[(stratum,srole,trole)].add(ident)
 if stratum=='old_explicit_shared_link' and d['original_form_number_term_eligible']:
  if not d['target_inside_larger_envelope'] and not d['original_envelope_reasons']:
   legacy['all_form_pairs'].add(ident);legacy['source_'+srole].add(ident);legacy['target_'+trole].add(ident)
   if srole==trole=='NOUN':legacy['both_noun'].add(ident)
  if d['target_inside_larger_envelope']:
   span['smaller_target_form_pairs'].add(ident)
   if srole==trole=='NOUN':span['both_roles_noun'].add(ident)
   for reason in d['exact_focus_reasons']:span['reason_'+reason].add(ident)
 if stratum=='new_direct_english_unresolved_candidate':
  assert d['source_entry_resolved'] is False and d['source_sense_id'] is None and 'source_form_ref' not in d and 'number_agrees' not in d
  assert 'form_id' not in sr and 'lexeme_id' not in sr
  direct['candidate_relation_ids'].add(d['candidate_relation']['relation_id']);direct['pairs'].add(d['pair_id']);direct['components'].add(d['component']);direct['source_focuses'].add((sr['endpoint_key'],tuple(sr['actual_form_utf16'])));direct['heads'].add(d['head'])
result={'complete':True,'join_receipt_sha256':sha(R/'join-r02/receipt.json'),'evidence_sha256':sha(path),'evidence_bytes':path.stat().st_size,'failed_prefix_sha256':sha(old),'failed_prefix_exact_containment':containment,'relation_rows_by_stratum':dict(counts),'distinct_head_observation_form_pair_role_patterns':[{'stratum':k[0],'source_role':k[1],'target_role':k[2],'count':len(v)} for k,v in sorted(patterns.items())],'legacy_eligible_envelope_form_pairs':{k:len(v) for k,v in sorted(legacy.items())},'smaller_target_form_evidence':{k:len(v) for k,v in sorted(span.items())},'direct_unresolved_evidence':{k:len(v) for k,v in sorted(direct.items())},'limits':'Distinct form-pair counts overlap across readings/strata; role errors are not judged here. No semantic approval. No deletion of failed DB.','seconds':time.monotonic()-start,'VmHWM_bytes':int(next(s.split()[1] for s in Path('/proc/self/status').read_text().splitlines() if s.startswith('VmHWM:')))*1024};db.close();out=R/'post-audit-r02.json';b=(json.dumps(result,indent=2)+'\n').encode();assert len(b)<2*1024**2
with out.open('xb') as f:f.write(b)
print(json.dumps(result))
