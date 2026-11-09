#!/usr/bin/env python3
"""Private additive candidates; never writes shipped assets or native policy."""
import argparse,copy,hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[3]
PINS={'qa/immersion/coverage_ceiling_experiment/content-expansion-candidate-r01.json':'5264106ac021932f97350767a792a53e74cdac2fed4242997c9e771a683508a4','qa/immersion/coverage_ceiling_experiment/content-expansion-concept-group-audit-r02.json':'21efcaf302c22980752d52b486d8ea04e30c2e62a82822707e8e18f625ce4782','data/immersion/starter-en-ja-002.json':'62e147bdad14a8f2bc96de2099fa7977c3e125ef5ef6870c34e1d2716128807e','data/immersion/starter-en-sw-001.json':'e0103acd530f6c4c121e7a976de954fe1e115a1083c6605c680b1e649c7c74b0'}
def encoded(x):return (json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();assert not a.output.exists();assert R not in a.output.resolve().parents
 data={}
 for n,h in PINS.items():
  raw=(R/n).read_bytes();assert sha(raw)==h;data[n]=json.loads(raw)
 candidate=data[next(iter(PINS))];groupfile='qa/immersion/coverage_ceiling_experiment/content-expansion-concept-group-audit-r02.json';groups=data[groupfile]['alias_groups'];canonical={v:g[0] for g in groups for v in g}
 result={};writes={}
 for lang,old,version,total in [('ja','starter-en-ja-002.json','starter-en-ja-003',193),('sw','starter-en-sw-001.json','starter-en-sw-002',217)]:
  active=data['data/immersion/'+old];p=copy.deepcopy(active);entries=p['entries'];active_ids={e['id'] for e in entries};old_by={e['id']:e for e in candidate['pairs']['en-'+lang]['entries']};proofs=[]
  for e in entries:
   for k in ['source','target','reading','reading_kana','concept_id','pos','category','train_rank','source_tokens','guard','following']:assert e.get(k)==old_by[e['id']].get(k)
   assert canonical.get(e['concept_id'],e['concept_id'])==e['concept_id'],'active concept migration requires separate review'
  for e in old_by.values():
   if e['id'] in active_ids or e['source']=='winter':continue
   assert e.get('primary_evidence');assert len(e['source_tokens'])==1
   if lang=='ja':assert e.get('reading') and e.get('reading_kana')
   concept=canonical.get(e['concept_id'],e['concept_id'])
   proof={'candidate_sha256':PINS[next(iter(PINS))],'original_entry':e,'canonical_concept_id':concept,'alias_audit_sha256':PINS[groupfile]}
   record=sha(encoded(proof));proofs.append({'entry_id':e['id'],'record_sha256':record,'evidence':proof})
   x={k:e[k] for k in ['id','source','target','category','pos','train_rank','source_tokens']};x.update({k:e[k] for k in ['guard','following','reading','reading_kana'] if k in e});x.update(concept_id=concept,record_sha256=record);entries.append(x)
  assert entries[:len(active['entries'])]==active['entries'];assert len(entries)==total and len({e['id'] for e in entries})==total
  assert all(e['source']!='winter' for e in entries)
  forbidden={'word-en-ja-month','word-en-ja-months','word-en-ja-expensive'} if lang=='ja' else {'word-en-sw-thing','word-en-sw-things','word-en-sw-here','word-en-sw-sports'}
  assert not forbidden & {e['id'] for e in entries}
  p.update(version=version,activation=False,selection='Current qualified native greedy whole-unit packing; no policy change.',candidate_parent_sha256=PINS[next(iter(PINS))],active_parent_sha256=PINS['data/immersion/'+old],concept_alias_audit_sha256=PINS[groupfile],withheld_original_entry_ids=['word-en-'+lang+'-winter'],qualification_status='Private candidate only; not promoted')
  raw=encoded(p);manifest={'schema':'vipi-source-starter-manifest-1','file':version+'.json','sha256':sha(raw),'bytes':len(raw),'version':version,'entries':total}
  writes[version+'.json']=raw;writes['starter-'+lang+'-candidate-manifest.json']=encoded(manifest);writes['proofs-'+lang+'.json']=encoded(proofs)
  result[lang]={'manifest':manifest,'active_entries_unchanged':len(active['entries']),'additions':len(proofs),'preserved_exclusions':sorted(forbidden),'active_concept_ids':sorted({e['concept_id'] for e in active['entries']}),'candidate_concept_ids':sorted({e['concept_id'] for e in entries}),'source_context_sets_unchanged':p['source_context_sets']==active['source_context_sets']}
 assert sum(map(len,writes.values()))<4*1024**2
 a.output.mkdir(parents=True)
 for name,raw in writes.items():(a.output/name).write_bytes(raw)
 receipt={'compiler_sha256':sha(Path(__file__).read_bytes()),'inputs':PINS,'alias_groups':groups,'results':result,'files':{n:{'sha256':sha(b),'bytes':len(b)} for n,b in writes.items()},'runtime_changes':False,'shipped_assets_written':False}
 (a.output/'receipt.json').write_bytes(encoded(receipt));print(json.dumps({l:r['manifest'] for l,r in result.items()}))
if __name__=='__main__':main()
