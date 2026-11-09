"""Read-only post-run qualification; never changes frozen predictions or inference."""
import collections,functools,hashlib,json,os,re,resource,signal,sqlite3,time
from pathlib import Path
R=Path('/srv/fallsoft/staging/vipi-apertium-lexical-selection-20261109-r01');N=Path('/srv/fallsoft/staging/vipi-contextual-lexical-selection-20261109-r01');C=Path('/srv/fallsoft/staging/vipi-apertium-corpus-evidence-20261109-r01')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def main():
 start=time.monotonic();os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});os.nice(10);resource.setrlimit(resource.RLIMIT_AS,(1024**3,)*2);signal.alarm(120);out=R/'morphology-audit-r02';out.mkdir(exist_ok=False);receipt=json.loads((R/'cohort/receipt.json').read_text());assert receipt['complete'];assert sha(R/'cohort/predictions.json')==receipt['outputs']['predictions.json']['sha256'];assert sha(C/'join-r02/evidence.sqlite')=='03415f4547ed645a9dc5e9283ab4bfb77621e8ebb801f46f608a75b6053b01e3';assert sha(N/'prepare/dataset.json')=='f2dbf75de3f38cb223c012f444fe7b4e6713eaf22ec0f8f41375384362ec0cfa';data=json.loads((N/'prepare/dataset.json').read_text());source={x['id']:x for x in data['rows']};preds=json.loads((R/'cohort/predictions.json').read_text());db=sqlite3.connect((C/'join-r02/evidence.sqlite').as_uri()+'?mode=ro&immutable=1',uri=True);db.execute('PRAGMA query_only=ON');details=[];counts=collections.defaultdict(collections.Counter);pairs={};changedqualified=collections.Counter()
 @functools.lru_cache(maxsize=10000)
 def obj(ref):return json.loads(db.execute('SELECT data FROM objects WHERE id=?',(ref,)).fetchone()[0])
 def tags(a):return re.findall(r'<([^>]+)>',a)
 def lemma(a):return ' '.join(re.sub(r'<[^>]+>','',a).casefold().split())
 def gender(ts):return set(ts)&{'m','f','nt','mf','GD'}
 for p in preds:
  for method,m in p['methods'].items():
   if m['target'] is None:counts[method]['no_emitted_face']+=1;continue
   selected=m['chosen_analysis'];st=tags(selected);analyses=collections.defaultdict(lambda:{'relation_refs':set(),'raw_analysis_refs':set(),'pair_ids':set()})
   for ref in m['train_supported_faces'][m['target']]:
    relation=obj(ref);tr=relation['target_role']
    for rid in tr['raw_analysis_refs']:
     u=obj(rid)
     if u['utf16']!=tr['actual_form_utf16'] or len(u['contextual_readings'])!=1:continue
     a=u['contextual_readings'][0]
     if lemma(a)!=lemma(selected):continue
     value=analyses[a];value['relation_refs'].add(ref);value['raw_analysis_refs'].add(rid);value['pair_ids'].add(relation['pair_id'])
   assert analyses;exact=[a for a in analyses if tags(a)==st];sg=gender(st);flags=set()
   for a in analyses:
    at=tags(a);ag=gender(at)
    if st==at:flags.add('exact_all_tags_supported');continue
    flags.add('tag_difference')
    if sg in ({'m'},{'f'},{'nt'}) and ag in ({'m'},{'f'},{'nt'}) and sg!=ag:flags.add('explicit_gender_incompatible')
    elif sg!=ag:flags.add('gender_GD_mf_or_unspecified_difference')
    if [t for t in st if t not in {'m','f','nt','mf','GD'}]!=[t for t in at if t not in {'m','f','nt','mf','GD'}]:flags.add('other_tag_difference')
   qualified=bool(exact);counts[method]['emitted_face']+=1;counts[method]['qualified_exact_tags' if qualified else 'unqualified_tag_identity']+=1
   for flag in flags:counts[method][flag]+=1
   x=source[p['id']];value={'id':p['id'],'method':method,'target':m['target'],'selected_analysis':selected,'selected_tags':st,'qualified_exact_tags':qualified,'flags':sorted(flags),'source_endpoint':x['endpoint'],'source_utf16':x['span'],'actual_source':data['endpoints'][x['endpoint']],'retained_candidate_analyses':{a:{k:sorted(v) for k,v in d.items()} for a,d in sorted(analyses.items())},'not_a_semantic_label':True};details.append(value)
   if not qualified:
    for d in analyses.values():
     for pid in d['pair_ids']:pairs[pid]=data['pairs'][pid]
 summary={'counts':{k:dict(v) for k,v in counts.items()},'definition':'Exact all-tag match on at least one actually retained same-face analysis qualifies; conflicting/underspecified differences retained separately. A tag difference is not automatically a semantic error; GD/mf/unspecified is distinct from explicit incompatible m/f/nt. Original lemma/number predictions immutable.','input_predictions_sha256':sha(R/'cohort/predictions.json')};proof_sets={};source_contexts={};compact=[]
 for value in details:
  original_hash=hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest();proof=value['retained_candidate_analyses'];ref=hashlib.sha256(json.dumps(proof,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest();proof_sets.setdefault(ref,proof);source_contexts.setdefault(value['source_endpoint'],value['actual_source']);v={k:x for k,x in value.items() if k not in ('retained_candidate_analyses','actual_source')};v.update(proof_set_ref=ref,source_context_ref=value['source_endpoint'],original_expanded_record_sha256=original_hash);reconstructed={k:x for k,x in v.items() if k not in ('proof_set_ref','source_context_ref','original_expanded_record_sha256')};reconstructed.update(retained_candidate_analyses=proof_sets[ref],actual_source=source_contexts[value['source_endpoint']]);assert reconstructed==value;compact.append(v)
 summary['representation']={'expanded_records':len(details),'compact_records':len(compact),'unique_proof_sets':len(proof_sets),'unique_source_contexts':len(source_contexts),'exact_reconstruction_all_records':True,'unqualified_training_pair_references':len(pairs)}
 values={'summary.json':summary,'all-emitted-form-audit.json':compact,'candidate-proof-sets.json':proof_sets,'source-contexts.json':source_contexts,'unqualified-training-witness-references.json':{'immutable_dataset':str(N/'prepare/dataset.json'),'dataset_sha256':'f2dbf75de3f38cb223c012f444fe7b4e6713eaf22ec0f8f41375384362ec0cfa','pair_ids':sorted(pairs),'full_pair_records_retained_in_dataset':True}}
 encoded={name:(json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode() for name,value in values.items()};prospective={'output_bytes':sum(len(b) for b in encoded.values()),'files':{name:len(b) for name,b in encoded.items()},'same_qualification_predicate':True,'exact_expanded_record_reconstruction':True};(out/'prospective-size.json').write_text(json.dumps(prospective,indent=2)+'\n')
 for name,value in values.items():
  raw=encoded[name];assert sum(p.stat().st_size for p in out.iterdir() if p.is_file())+len(raw)<24*1024**2;assert sum(p.stat().st_size for p in R.rglob('*') if p.is_file())+len(raw)<64*1024**2;(out/name).write_bytes(raw)
 db.close();result={'complete':True,'seconds':time.monotonic()-start,'VmHWM_bytes':int(next(s.split()[1] for s in Path('/proc/self/status').read_text().splitlines() if s.startswith('VmHWM:')))*1024,'code_sha256':sha(Path(__file__)),'outputs':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file()},'packet_sha256':sha(R/'cohort/blind-review-packet.json')};(out/'receipt.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
