#!/usr/bin/env python3
"""Join two frozen semantic reviews; retain raw labels and no majority gold."""
import collections,hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
W=Path('/home/ai/Development/investigations/vipi-tatoeba-domain-comparison-20261108-r01/review-evidence-r01')
EXPECTED={'review-packet.json':'4134b20abfed4ac15ae63aa34111631bc8ccafcd94caed9752eb77639fc5b247','author-review-r01.json':'007f76182288955d22f16719ffdfdab12a65fd4d5dc1df990445ccb16e0f450b','root-review-r01.json':'63487457e8ec0e578ccf63b31e190008c928c2d1e275b9d02d7326c4005ec159'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 for name,h in EXPECTED.items():assert sha(W/name)==h
 packet=json.loads((W/'review-packet.json').read_text());a=json.loads((W/'author-review-r01.json').read_text());r=json.loads((W/'root-review-r01.json').read_text())
 assert a['packet_sha256']==r['packet_sha256']==EXPECTED['review-packet.json']
 author={c['review_id']:c for c in a['cases']};root={c['review_id']:c for c in r['cases']};assert len(author)==len(root)==32
 addendum=json.loads((W/'root-review-notes-addendum-r01.json').read_text());assert addendum['root_review_sha256']==EXPECTED['root-review-r01.json'] and addendum['labels_changed'] is False
 joined=[];disagreements=[];summary={who:{} for who in ['author','root']}
 for c in packet['cases']:
  ident=c['review_id'];ac,rc=author[ident],root[ident];assert ac['corpus']==rc['corpus']==c['corpus'];assert ac['source_phrase']==c['source_phrase'] and ac['target_phrase']==c['target_phrase']
  same=c['source_phrase']==c['target_phrase'];assert ac['changed_face']==(not same)
  norm={'author':{'meaning':{'minor':'minor_difference','material':'material_error'}.get(ac['meaning'],ac['meaning']),'changed_usable':ac['minor_tolerant_pass'] and not same and ac['entity_identifier']!='changed_unverified'},'root':{'meaning':rc['meaning_in_attested_context'],'changed_usable':rc['usable_changed_output_minor_forms_allowed']}}
  axes=[axis for axis in ['meaning','changed_usable'] if norm['author'][axis]!=norm['root'][axis]]
  if axes:disagreements.append({'review_id':ident,'corpus':c['corpus'],'axes':axes,'normalized':norm})
  joined.append({'review_id':ident,'corpus':c['corpus'],'bucket':c['selection']['bucket'],'length':c['selection']['length'],'identical_face':same,'raw_author':ac,'raw_root':rc,'normalized':norm})
 for who in summary:
  for corpus in ['tatoeba','pgv']:
   rows=[c for c in joined if c['corpus']==corpus];counts=collections.Counter(c['normalized'][who]['meaning'] for c in rows)
   summary[who][corpus]={'denominator':len(rows),'meaning_counts':dict(counts),'changed_usable':sum(c['normalized'][who]['changed_usable'] for c in rows),'identical_faces':sum(c['identical_face'] for c in rows),'by_bucket':{bucket:{'denominator':sum(c['bucket']==bucket for c in rows),'changed_usable':sum(c['bucket']==bucket and c['normalized'][who]['changed_usable'] for c in rows)} for bucket in sorted({c['bucket'] for c in rows})}}
   if who=='author':summary[who][corpus]['accepted_changed_content']=sum(c['raw_author']['accepted_changed_content'] for c in rows);summary[who][corpus]['construction_scope_counts']=dict(collections.Counter(c['raw_author']['construction_scope'] for c in rows))
 private=W/'joined-reviews-r01.json'
 with private.open('x') as f:json.dump({'cases':joined,'root_wording_addendum':addendum},f,ensure_ascii=False,indent=2);f.write('\n')
 receipt={'schema':1,'production':False,'script_sha256':sha(Path(__file__)),'input_bindings':{name:{'path':str(W/name),'sha256':h} for name,h in EXPECTED.items()},'root_wording_addendum':{'path':str(W/'root-review-notes-addendum-r01.json'),'sha256':sha(W/'root-review-notes-addendum-r01.json'),'labels_changed':False},'private_join':{'path':str(private),'sha256':sha(private)},'summary':summary,'comparative_axis_disagreements':disagreements,'normalization':'Only material/minor spelling unified for meaning comparison; author minor may include form/register. Author changed-usable derives own minor-tolerant pass, actual face change and no unverified identity flag; root uses explicit whole-output usable-changed field. Raw labels, construction scope, role/form/completeness/utility and notes preserved unchanged. Root has no separate structured content-utility counts; do not fabricate them.','limits':['No majority gold or label replacement.','Shared source keys have different attested sentences; not same-context paired outcomes.','Stratified diagnostic sample with reused keys, not population accuracy.','Contextual semantic compatibility does not approve reusable phrase construction, vocabulary-only policy or native mask permission.','Same-face outputs earn no changed immersion credit.','No runtime grid or activation.']}
 with (HERE/'semantic-comparison-receipt-r01.json').open('x') as f:json.dump(receipt,f,ensure_ascii=False,indent=2);f.write('\n')
 print(json.dumps({'summary':summary,'disagreements':disagreements}))
if __name__=='__main__':main()
