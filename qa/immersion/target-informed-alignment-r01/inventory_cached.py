"""Read-only cached-target census; no target generation or alignment."""
import collections,hashlib,json,pathlib,unicodedata
B=pathlib.Path('/home/ai/Development/investigations');W=B/'vipi-target-informed-alignment-20261109-r01';Q=pathlib.Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
norm=lambda t:' '.join(unicodedata.normalize('NFC',t).casefold().split())
current={norm(x['source']) for x in json.loads((W/'mixed-outputs-and-deltas.json').read_text())['cases']}
items=[('taskmaster','vipi-android-readiness-20261107-r01/taskmaster-ceiling-001.json','qa/immersion/coverage_ceiling_experiment/taskmaster-native-protocol-r01.json'),('sms','vipi-android-readiness-20261107-r01/coverage-ceiling-001.json','qa/immersion/coverage_ceiling_experiment/native-protocol.json'),('conversation80','vipi-android-readiness-20261107-r01/conversational-routing-001.json','qa/immersion/coverage_ceiling_experiment/conversational-holdout-source-r01.json'),('directional','vipi-android-readiness-20261107-r01/directional-ceiling-001.json','qa/immersion/coverage_ceiling_experiment/directional-native-protocol-r01.json')]
out={};sets={};repo=Q.parents[2]
for name,f,protocol in items:
 p=B/f;j=json.loads(p.read_text());counts=collections.defaultdict(collections.Counter);textsets=collections.defaultdict(set)
 for x in j['cases']:
  pair=x['source']+'>'+x['target'];c=counts[pair];c['rows']+=1;t=norm(x['original']);textsets[pair].add(t);c['overlap_current8']+=t in current;c['native_source_geometry']+=bool(x.get('native_source_word_ranges'))
  targets={d.get('complete_translation') for d in x.get('densities',[]) if d.get('complete_translation')};c['has_full_target']+=bool(targets);c['multiple_full_targets_across_density_captures']+=len(targets)>1;c['target_variants']+=len(targets)
  c['explicit_protected_range_field']+=any('protect' in k for k in x)
 pr=repo/protocol;pj=json.loads(pr.read_text());out[name]={'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p),'complete':j.get('complete'),'provider':j.get('provider'),'input_sha256':j.get('input_sha256'),'protocol':{'path':str(pr),'sha256':sha(pr),'capture_input_hash_matches':sha(pr)==j.get('input_sha256')},'pairs':{k:dict(v,unique_normalized_sources=len(textsets[k])) for k,v in counts.items()},'protocol_metadata':{k:v for k,v in pj.items() if k not in ['messages','cases','requests','queries'] and not isinstance(v,list)}};sets[name]=set().union(*textsets.values())
out['overlap_between_collections']={a+'|'+b:len(sets[a]&sets[b]) for a in sets for b in sets if a<b}
# Retained authored/contrast cases are useful controls, not conversational coverage.
p=B/'vipi-immersion-reconciliation-20261107-r01/retained-mac-comparison/immersion-approach-comparison-001.json';j=json.loads(p.read_text());out['authored34']={'path':str(p),'sha256':sha(p),'bytes':p.stat().st_size,'pairs':dict(collections.Counter(x['source']+'>'+x['target'] for x in j['results'])),'full_targets':sum(bool(x.get('full')) for x in j['results']),'exposed_authored_diagnostics':True}
(W/'cached-cohort-inventory.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v.get('pairs',v) for k,v in out.items()},indent=2))
