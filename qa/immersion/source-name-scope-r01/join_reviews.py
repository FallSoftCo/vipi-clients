#!/usr/bin/env python3
"""Join independently frozen judgments without overwriting disagreements."""
import collections,hashlib,json
from pathlib import Path
W=Path('/home/ai/Development/investigations/vipi-source-name-scope-20261109-r01');Q=Path(__file__).resolve().parent
BINDINGS={'root-review-r01.json':'d13fdb3fe55a068660fa02c5f1455caeda6aeba779d4d30c9b76eae6c794bbf1','author-review-r01.json':'f875be1440bc271c38162466c770463a3929327d32095fe237d4a1015a737b5c','r02-evidence/packet-r02/review-packet.json':'683deace2caefe33addba06053a622f019f44095c742382c150ad8ad97c15c81','semantic-rubric-r01.json':'f544a478ced5c075ab1e059fdac9cfd14ffabc48cb0d731be30047d44ffd19fa'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def enc(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def key(u):return enc([u['focus_utf16'],u['source'],u['target'],u['reading']])
def write(p,x):
 with p.open('x') as f:json.dump(x,f,ensure_ascii=False,indent=2);f.write('\n')
def main():
 for name,h in BINDINGS.items():assert sha(W/name)==h
 root=json.loads((W/'root-review-r01.json').read_text());author=json.loads((W/'author-review-r01.json').read_text());packet=json.loads((W/'r02-evidence/packet-r02/review-packet.json').read_text())
 assert root['other_reviewer_labels_read']==author['other_reviewer_labels_read']==False
 for r in [root,author]:assert r['packet_sha256']==BINDINGS['r02-evidence/packet-r02/review-packet.json'] and r['rubric_sha256']==BINDINGS['semantic-rubric-r01.json']
 rm={c['review_id']:c for c in root['cases']};am={c['review_id']:c for c in author['cases']+author['development_controls']};rows=packet['cases']+packet['development_controls'];assert set(rm)==set(am)=={c['review_id'] for c in rows}
 joined=[];disagreements=[];outdiff=[];metrics=collections.defaultdict(collections.Counter);changes=collections.defaultdict(collections.Counter);counts=collections.Counter()
 for p in rows:
  ident=p['review_id'];r,a=rm[ident],am[ident];assert r['source_id']==a['source_id']==p['source_id'] and r['known']==a['known']==p['known'];group='development_controls' if p['development_control'] else 'sampled';assert r['group']==('development_controls' if p['development_control'] else 'cases')
  ru={key(u):u for u in r['units']};au={key(u):u for u in a['union']};assert set(ru)==set(au)=={key(u) for u in p['review_union']};units=[]
  for u in p['review_union']:
   k=key(u);rr,aa=ru[k],au[k];assert rr['arms']==aa['arms']==u['arms'];counts[group+':union']+=1
   transition='added' if u['arms']==['experimental'] else 'removed' if u['arms']==['baseline'] else 'retained'
   for reviewer,item in [('root',rr),('author',aa)]:changes[group+'|'+reviewer+'|'+p['known']][transition+':'+item['label']]+=1
   item={'identity':u,'transition':transition,'root_raw':rr,'author_raw':aa,'label_agreement':rr['label']==aa['label']};units.append(item)
   if not item['label_agreement']:disagreements.append({'review_id':ident,'group':group,'unit':item})
  whole={}
  for arm,data in p['arms'].items():
   rr,aa=r['outputs'][arm],a['whole_outputs'][arm];assert rr['mixed_output']==aa['mixed_output']==data['mixed_output'];nonempty=bool(data['selected_indices']);assert aa['nonempty']==nonempty
   assert rr['selected_indices']==data['selected_indices']
   rn=rr['label'] if nonempty else 'empty';an=aa['label'] if nonempty else 'empty'
   normalized={'root':{'label':rn,'strict':rr['strict_usable'],'minor_tolerant':rr['minor_tolerant_usable']},'author':{'label':an,'strict':aa['strict_nonempty_all_correct'],'minor_tolerant':aa['minor_tolerant_nonempty']}}
   for reviewer,n in normalized.items():
    c=metrics[group+'|'+reviewer+'|'+p['known']+'|'+arm];c['outputs']+=1;c['nonempty']+=nonempty;c['strict']+=n['strict'];c['minor_tolerant']+=n['minor_tolerant'];c['label:'+n['label']]+=1
   whole[arm]={'root_raw':rr,'author_raw':aa,'normalized':normalized}
   if normalized['root']!=normalized['author']:outdiff.append({'review_id':ident,'group':group,'arm':arm,'normalized':normalized})
  for reviewer in ['root','author']:
   for criterion in ['strict','minor_tolerant']:
    before=whole['baseline']['normalized'][reviewer][criterion];after=whole['experimental']['normalized'][reviewer][criterion]
    changes[group+'|'+reviewer+'|'+p['known']][criterion+':'+('gain' if after and not before else 'loss' if before and not after else 'both_pass' if before else 'both_fail')]+=1
  joined.append({'review_id':ident,'source_id':p['source_id'],'known':p['known'],'group':group,'union':units,'whole_outputs':whole})
 result={'production':False,'bindings':BINDINGS,'empty_normalization':'Root empty and author correct+nonempty=false normalize to empty only for outcome comparisons; original records retained. No other label normalization.','cases':joined,'unit_disagreements':disagreements,'whole_output_disagreements':outdiff,'metrics':{k:dict(v) for k,v in metrics.items()},'paired_changes':{k:dict(v) for k,v in changes.items()},'counts':dict(counts),'limits':'No majority gold, label overwrite or population accuracy. Exposed controls separate from stratified sampled changes.'};write(W/'joined-review-r01.json',result)
 summary={k:result[k] for k in ['bindings','empty_normalization','metrics','paired_changes','counts','limits']};summary.update(joined_review_path=str(W/'joined-review-r01.json'),joined_review_sha256=sha(W/'joined-review-r01.json'),unit_disagreements=[{'review_id':d['review_id'],'group':d['group'],'source':d['unit']['identity']['source'],'target':d['unit']['identity']['target'],'root':d['unit']['root_raw']['label'],'root_rationale':d['unit']['root_raw']['rationale'],'author':d['unit']['author_raw']['label'],'author_rationale':d['unit']['author_raw']['note']} for d in disagreements],whole_output_disagreements=outdiff,raw_availability=json.loads((W/'r02-evidence/project-r02/metrics.json').read_text()),execution_receipts={stage:json.loads((W/'r02-evidence'/stage/'receipt.json').read_text()) for stage in ['catalog-r02','project-r02','packet-r02']},script_sha256=sha(Path(__file__)))
 write(Q/'result.json',summary);print(json.dumps({'counts':summary['counts'],'unit_disagreements':summary['unit_disagreements'],'whole_output_disagreements':outdiff,'metrics':summary['metrics'],'paired_changes':summary['paired_changes']},indent=2,ensure_ascii=False))
if __name__=='__main__':main()
