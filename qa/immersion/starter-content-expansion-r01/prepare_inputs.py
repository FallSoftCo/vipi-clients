#!/usr/bin/env python3
"""Freeze reused inputs and authored contrasts; no native matching or predictions."""
import json,gzip,hashlib,datetime
from pathlib import Path
R=Path(__file__).resolve().parents[3];W=Path('/home/ai/Development/investigations/vipi-starter-content-expansion-20261109-r01');P=Path('/home/ai/Development/investigations/vipi-starter-packing-density-20261109-r01/inputs')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def encode(x):return (json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
CONTROLS=[
 ('root-school-ordinary','My daughter starts school tomorrow.',['school']),
 ('root-school-conflict','A school of fish swam past us.',['school']),
 ('root-apple-ordinary','I cut an apple for lunch.',['apple','lunch']),
 ('root-apple-name','Apple announced a new phone.',['apple']),
 ('root-jobs-ordinary','There are jobs near my house.',['jobs','house']),
 ('root-jobs-name','Jobs changed personal computing.',['jobs']),
 ('root-nurse-ordinary','I need a nurse for my child.',['nurse']),
 ('root-nurse-role','I nurse my child at home.',['nurse']),
 ('root-duration','We lived there for two years.',['years']),
 ('root-kinship','How is your dad today?',['dad']),
 ('author-eat','I eat bread after work.',['eat','bread']),
 ('author-sing-swim','We sing together and swim every week.',['sing','swim']),
 ('author-prefer-understand','I prefer tea, but I understand your choice.',['prefer','understand']),
 ('author-believe-remember','I believe you and remember that day.',['believe','remember']),
 ('author-year','That was a good year for our family.',['year']),
 ('author-first-ordinal','The first day of school is easy.',['first','day','school','easy']),
 ('author-first-function','Please call me first.',['first']),
 ('author-house-role','We house the animals near the lake.',['house','lake']),
 ('author-water-noun','The water in that glass is cold.',['water']),
 ('author-water-role','I water the plants every morning.',['water']),
 ('author-literals','Keep `apple` and https://example.test/school unchanged.',['apple','school']),
 ('author-repetition','The school has a garden, and the school has a library.',['school','garden']),
 ('author-negation','I do not believe the story, and I do not want cheese.',['believe','story','cheese']),
 ('author-multiword-boundary','What kind of art do they also prefer?',['art','prefer'])]
def main():
 out=W/'inputs-r02';assert not out.exists();out.mkdir();pins={};cases={};witness=[];availability=[]
 historical=R/'qa/immersion/coverage_ceiling_experiment/content-expansion-evidence-r01/content-expansion-fresh-all237-review-r01.json.gz';pins[str(historical)]=sha(historical);old=json.load(gzip.open(historical,'rt'))['rows']
 allstates={};overlaps={}
 for lang in ['ja','sw']:
  path=P/(lang+'-baseline.json');pins[str(path)]=sha(path);prior=json.loads(path.read_text())['cases'];rows=[x for x in prior if x['known_state']==0];assert len(rows)==128
  x=[{'id':'retained128/'+r['id'],'original_id':r['id'],'source':r['original'],'stratum':'retained128/'+r['stratum'],'historically_exposed':True} for r in rows]
  historical_rows=[r for r in old if r['target_language']==lang];assert len(historical_rows)==79
  for h in historical_rows:
   identifier='historical79/'+h['source_case_id'];x.append({'id':identifier,'original_id':h['id'],'source':h['source'],'stratum':'historical79/'+h['sampling_length_bin'],'historically_exposed':True});witness.append({'pair':'en-'+lang,'id':identifier,'preceding_source_context':h['review_only_preceding_context'],'historical_scope_ids':[s['scope_id'] for s in h['scopes']]})
  for ident,text,forms in CONTROLS:
   prior_ids=[r['id'] for r in x if r['source']==text]
   x.append({'id':'authored24/'+ident,'original_id':ident,'source':text,'stratum':'authored_contrast_control','historically_exposed':bool(prior_ids),'prior_exact_source_ids':prior_ids,'authored_before_output':True})
  assert len(x)==231 and len({z['id'] for z in x})==231
  candidate=W/'candidates-r01'/('starter-en-ja-003.json' if lang=='ja' else 'starter-en-sw-002.json');pins[str(candidate)]=sha(candidate);pack=json.loads(candidate.read_text());by={e['source'].casefold():e for e in pack['entries']};assert len(by)==len(pack['entries'])
  for ident,text,forms in CONTROLS:
   availability.append({'pair':'en-'+lang,'id':'authored24/'+ident,'focus_inventory':[{'source_form':s,'candidate_entry_id':by.get(s,{}).get('id'),'available':s in by} for s in forms],'not_native_admission_or_correctness':True})
  active=R/'data/immersion'/('starter-en-ja-002.json' if lang=='ja' else 'starter-en-sw-001.json');pins[str(active)]=sha(active);current=json.loads(active.read_text())
  legacy=next(r['known_ids'] for r in prior if r['known_state']==1)
  allstates['en-'+lang]=[{'id':'none','known_ids':[]},{'id':'historical_selected_exclusions','known_ids':legacy},{'id':'current_pack_excluded_tail_diagnostic','known_ids':sorted({e['concept_id'] for e in current['entries']}),'not_familiarity':True}]
  cases['en-'+lang]=x;sets=[{r['source'] for r in x if r['stratum'].startswith(prefix)} for prefix in ['retained128/','historical79/','authored_contrast_control']]
  overlaps['en-'+lang]={'rows':len(x),'unique_source_texts':len({z['source'] for z in x}),'retained128_historical79_exact_overlap':len(sets[0]&sets[1]),'controls_previous_exact_overlap':len(sets[2]&(sets[0]|sets[1])),'no_rows_removed':True}
 controls={'frozen_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'before_native_output':True,'controls':[{'id':i,'source':t,'tracked_forms':f,'author':'root' if i.startswith('root-') else 'author_agent'} for i,t,f in CONTROLS]}
 values={'comparison-inputs.json':{'pairs':cases,'states':allstates,'densities':[0.25,0.75],'input_use':'All historical rows are reused diagnostic evidence, no fresh corpus claim. Controls authored before outputs.'},'source-witnesses.json':witness,'control-availability.json':availability,'controls-freeze.json':controls}
 for n,x in values.items():(out/n).write_bytes(encode(x))
 receipt={'script_sha256':sha(Path(__file__)),'bindings':pins,'overlap':overlaps,'files':{n:{'sha256':sha(out/n),'bytes':(out/n).stat().st_size} for n in values},'base_comparison_cells':462*3*2,'native_evaluations_two_arms':462*3*2*2,'native_execution':False};(out/'receipt.json').write_bytes(encode(receipt));print(json.dumps(receipt['overlap']));print('manifest',sha(out/'receipt.json'))
if __name__=='__main__':main()
