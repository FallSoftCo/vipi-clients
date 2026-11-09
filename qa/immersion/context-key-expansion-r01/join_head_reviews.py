#!/usr/bin/env python3
"""Join independently frozen reviews; preserve originals, never vote labels."""
import collections,hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
W=Path('/home/ai/Development/investigations/vipi-context-key-expansion-20261109-r01/head-preparation-r01')
EXPECTED={'packet':'3032eeb91acb02a7dfb265dde0dcac5615d1c1ded4e20b6a7cedd191bade2d95','author':'0e202c3c246a00fa97ff56ca355c251979d714de061dc02a1790f8c8850a9ece','root':'41d91b74a9623f265f981ffe60382f2f11c2d228eb5a0b261830b126b4d87169'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def enc(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def unit_key(u):return enc([u['focus_utf16'],u['target'],u['reading']])
def write(p,x):
 with p.open('x') as f:json.dump(x,f,ensure_ascii=False,indent=2);f.write('\n')
def main():
 paths={'packet':W/'r02-evidence/packet-r02/review-packet.json','author':W/'author-review-r01.json','root':W/'root-review-r01/root-review.json'}
 for name,p in paths.items():assert sha(p)==EXPECTED[name]
 p,a,r=[json.loads(paths[k].read_text()) for k in ['packet','author','root']]
 for review in [a,r]:assert review['packet_sha256']==EXPECTED['packet'] and not review['other_reviewer_labels_read']
 maps={name:{c['review_id']:c for c in data['cases']} for name,data in [('author',a),('root',r)]}
 assert all(set(m)=={c['review_id'] for c in p['cases']} for m in maps.values())
 aggregates={name:collections.Counter() for name in maps};changes={name:collections.Counter() for name in maps};joined=[];disagreements=[];whole_disagreements=[];both_nonempty={name:collections.Counter() for name in maps}
 for case in p['cases']:
  ident=case['review_id'];unit_maps={name:{unit_key(u):u for u in m[ident]['units']} for name,m in maps.items()}
  assert all(set(m)=={unit_key(u) for u in case['review_union']} for m in unit_maps.values())
  units=[]
  for index,u in enumerate(case['review_union']):
   originals={name:m[unit_key(u)] for name,m in unit_maps.items()};labels={'author':originals['author']['overall'],'root':originals['root']['label']}
   for name,label in labels.items():
    assert label in ['correct','minor_issue','material_error','uncertain'];aggregates[name]['unit:'+label]+=1
    for arm in u['arms']:assert arm in ['fixed','expanded']
    if u['arms']==['expanded']:changes[name]['added:'+label]+=1
    elif u['arms']==['fixed']:changes[name]['removed:'+label]+=1
    else:changes[name]['retained:'+label]+=1
   if len(set(labels.values()))>1:disagreements.append({'review_id':ident,'unit_index':index,'labels':labels})
   units.append({'unit_index':index,'identity':u,'raw_reviews':originals,'normalized_labels':labels})
  outputs={}
  for name,m in maps.items():
   raw=m[ident]['outputs' if name=='author' else 'arms'];norm={}
   for arm in ['fixed','expanded']:
    x=raw[arm];n={'nonempty':x['nonempty'],'label':x['overall'] if name=='author' else x['whole_output_label'],'strict':x['strict_all_correct_nonempty'] if name=='author' else x['strict_correct'],'minor_tolerant':x['all_correct_or_minor_nonempty'] if name=='author' else x['minor_tolerant_usable']}
    labels=[u['normalized_labels'][name] for u in units if arm in u['identity']['arms']]
    assert n['nonempty']==bool(case['arms'][arm]['selected_indices'])==bool(labels)
    assert n['strict']==(bool(labels) and all(v=='correct' for v in labels))
    assert n['minor_tolerant']==(bool(labels) and all(v in ['correct','minor_issue'] for v in labels))
    aggregates[name][arm+':'+n['label']]+=1;aggregates[name][arm+':strict']+=n['strict'];aggregates[name][arm+':minor_tolerant']+=n['minor_tolerant'];norm[arm]=n
   for axis in ['strict','minor_tolerant']:
    before,after=norm['fixed'][axis],norm['expanded'][axis];changes[name][axis+':'+('gain' if after and not before else 'loss' if before and not after else 'both_pass' if before else 'both_fail')]+=1
    if all(norm[arm]['nonempty'] for arm in norm):
     both_nonempty[name]['fixed:'+axis]+=before;both_nonempty[name]['expanded:'+axis]+=after
   if all(norm[arm]['nonempty'] for arm in norm):both_nonempty[name]['cases']+=1
   outputs[name]={'originals':raw,'normalized':norm}
  if outputs['author']['normalized']!=outputs['root']['normalized']:whole_disagreements.append(ident)
  joined.append({'review_id':ident,'source_id':case['source_id'],'known':case['known'],'stratum':case['stratum'],'units':units,'outputs':outputs})
 result={'production':False,'input_hashes':EXPECTED,'original_review_paths':{k:str(v) for k,v in paths.items()},'cases':joined,'unit_disagreements':disagreements,'whole_output_disagreements':whole_disagreements,'aggregates':{k:dict(v) for k,v in aggregates.items()},'paired_and_unit_changes':{k:dict(v) for k,v in changes.items()},'both_nonempty':{k:dict(v) for k,v in both_nonempty.items()},'rule':'Original labels/notes/axes retained; normalization only matches defined corresponding fields. No voting, accuracy estimate, or retroactive edits.'}
 dest=W/'joined-review-r01.json';write(dest,result)
 metrics=json.loads((W/'r02-evidence/project-r02/metrics.json').read_text());selection=json.loads((W/'r02-evidence/project-r02/review-selection-freeze.json').read_text());raw={}
 for known in ['all_function','all_function_global300']:
  before,after=metrics['fixed|'+known],metrics['expanded|'+known];assert before['messages']==after['messages']==9535
  raw[known]={'denominator_messages':9535,'fixed':before,'expanded':after,'net_nonempty_gain':after['nonempty']-before['nonempty'],'net_changed_words_gain':after['changed_words']-before['changed_words'],'paired_changed_outputs':selection['counts'][known+':changed'],'empty_to_nonempty':selection['counts']['empty_gain|'+known],'emitted_depth_loss_cases':selection['counts'].get('depth_loss|'+known,0)}
 summary={'production':False,'activation':False,'joined_path':str(dest),'joined_sha256':sha(dest),'script_sha256':sha(Path(__file__)),'input_hashes':EXPECTED,'review_cases':len(joined),'review_unique_emissions':sum(len(c['units']) for c in joined),'review_whole_outputs':2*len(joined),'unit_disagreements':disagreements,'whole_output_disagreements':whole_disagreements,'review_aggregates':result['aggregates'],'review_paired_and_unit_changes':result['paired_and_unit_changes'],'both_nonempty_review':result['both_nonempty'],'all_messages_raw_availability':raw,'selection_shortages':selection['shortages'],'limits':['24 changed-case stratified reused-TRAIN cases, not representative population accuracy.','Raw reach/changed words are selection quantities, not usable meaning coverage.','Empty output has zero immersion credit.','No sampled emitted-depth losses occurred, but different valid units and occurrences can still be displaced.','Agreement of these two reviews does not establish gold labels or general safety.']}
 write(HERE/'head-joined-review-receipt-r01.json',summary)
 print(json.dumps(summary))
if __name__=='__main__':main()
