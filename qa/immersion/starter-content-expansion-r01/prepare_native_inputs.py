#!/usr/bin/env python3
import json,hashlib,shutil,re
from pathlib import Path
R=Path(__file__).resolve().parents[3];W=Path('/home/ai/Development/investigations/vipi-starter-content-expansion-20261109-r01');D=Path('/home/ai/Development/investigations/vipi-starter-packing-density-20261109-r01');C=Path('/home/ai/Development/investigations/vipi-starter-packing-comparison-20261109-r01')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def encoded(x):return (json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
def main():
 out=W/'native-inputs-r02';assert not out.exists();out.mkdir();packs={};parents={}
 for lang,active,candidate,am in [('ja','starter-en-ja-002.json','starter-en-ja-003.json','starter-catalog.json'),('sw','starter-en-sw-001.json','starter-en-sw-002.json','starter-sw-catalog.json')]:
  packs[lang]={}
  for arm,pp,mp in [('current',R/'data/immersion'/active,R/'data/immersion'/am),('candidate',W/'candidates-r01'/candidate,W/'candidates-r01'/('starter-'+lang+'-candidate-manifest.json'))]:
   pn=arm+'-'+lang+'.json';mn=arm+'-'+lang+'-manifest.json';shutil.copyfile(pp,out/pn);shutil.copyfile(mp,out/mn);packs[lang][arm]={'pack':pn,'manifest':mn};parents[str(pp)]=sha(pp);parents[str(mp)]=sha(mp)
 p=W/'inputs-r02/comparison-inputs.json';shutil.copyfile(p,out/p.name);parents[str(p)]=sha(p);inputs=json.loads(p.read_text());states={pair:[s['id'] for s in values] for pair,values in inputs['states'].items()}
 oldp=C/'android-capture-r01/output.stdout';parents[str(oldp)]=sha(oldp);old={(x['pair'],x['id'],x['known_state']):x for x in json.loads(oldp.read_text())['cases']}
 raw=D/'android-capture-r01/output.stdout';parents[str(raw)]=sha(raw);expected={};known_differences={}
 for line in raw.open():
  row=json.loads(line);key=f"{row['pair']}/retained128/{row['id']}/{states[row['pair']][row['known_state']]}";known=inputs['states'][row['pair']][row['known_state']]['known_ids'];difference=set(known)^set(row['known_ids']);lang=row['pair'].split('-')[1]
  if difference:
   concepts=set()
   for arm in ['current','candidate']:
    pack=json.loads((out/packs[lang][arm]['pack']).read_text());concepts.update(e['concept_id'] for e in pack['entries'])
   assert not difference & concepts
   dk=row['pair']+'/'+states[row['pair']][row['known_state']];value={'historical_known_ids':sorted(row['known_ids']),'current_known_ids':sorted(known),'difference':sorted(difference),'absent_from_both_packs':True}
   assert dk not in known_differences or known_differences[dk]==value
   known_differences[dk]=value
  for step in row['steps']:
   if step['density_bits'] not in ['3fd0000000000000','3fe8000000000000']:continue
   result={'direct_spans':row['outputs'][step['output']]['spans']}
   if step['density_bits']=='3fd0000000000000':result['route_spans']=old[row['pair'],row['id'],row['known_state']]['b_spans']
   expected[key+'/'+step['density_bits']]=result
 assert len(expected)==1536;(out/'baseline-expected.json').write_bytes(encoded(expected))
 sp=D/'android-capture-r01/status.stdout';parents[str(sp)]=sha(sp);slider=json.loads(sp.read_text())['actual_slider_values']
 potential=[pair+'/'+c['id'] for pair,cases in inputs['pairs'].items() for c in cases if re.search(r'\bwhat\s+kind\b',c['source'],re.I)];assert len(potential)==6
 manifest={'schema':1,'files':{p.name:sha(p) for p in out.iterdir()},'packs':packs,'boundary_candidates':potential,'android_density_values':slider,'apple_density_values':[n/20 for n in range(16)],'states':states,'base_rows':1386,'base_paired_cells':2772,'maximum_arm_evaluations':6048,'expected_baseline_direct_parity':1536,'expected_baseline_route_parity':768,'parent_bindings':parents,'baseline_known_snapshot_differences':known_differences,'baseline_parity_scope':'Exact outputs with identical effective exclusions; raw historical known snapshots/cache identities differ as recorded.','candidate_activation':False,'schema_contract':'rows/steps/outputs/evidence; UTF16 scopes; direct and route separately; preserve unavailable and known-state rows'}
 (out/'native-input-manifest.json').write_bytes(encoded(manifest));print('manifest',sha(out/'native-input-manifest.json'),'bytes',sum(p.stat().st_size for p in out.iterdir()))
if __name__=='__main__':main()
