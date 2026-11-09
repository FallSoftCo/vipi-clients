"""Physically separate anonymous mixed messages, methods and parallel evidence."""
from common import *
import sqlite3,zlib

def main(r):
 r.verify();project=r.prior('project');prepared=r.prior('prepare');lookup=json.loads((prepared/'lookup.json').read_text());selection=json.loads((project/'review-selection-freeze.json').read_text());picks=[dict(x,development_control=False) for x in selection['selected']]+[{'id':ident,'known':known,'development_control':True,'stratum':'exposed_development'} for ident in r.p['development_source_ids'] for known in KNOWN];wanted={x['id'] for x in picks};rows={};delta={}
 with gzip.open(r.paths['trace'],'rt') as f,gzip.open(project/'decisions.jsonl.gz','rt') as g:
  for a,b in zip(f,g,strict=True):
   t=json.loads(a);d=json.loads(b);assert t['id']==d['id']
   if t['id'] in wanted:rows[t['id']]=t;delta[t['id']]=d
 assert set(rows)==wanted;conversations=json.loads(r.paths['source_context'].read_text());data=json.loads(r.paths['dataset'].read_text());databyid={x['id']:x for x in data['rows']};db=sqlite3.connect(r.paths['heads'].as_uri()+'?mode=ro&immutable=1',uri=True);cases=[];methodkey=[];witness={'contexts':{},'rules':{},'training_pairs':{},'case_references':{}}
 for i,pick in enumerate(picks,1):
  t=rows[pick['id']];d=delta[pick['id']];known=pick['known'];arms={'baseline':t['decisions'][known]['baseline'],'unrestricted':t['decisions'][known]['experimental'],'qualified':d['qualified'][known]};outputs=sorted({v['mixed_output'] for v in arms.values()},key=lambda s:digest(['qualified-options',pick['id'],known,s]));options=[{'option_id':chr(65+j),'mixed_output':text,'zero_immersion':all(not v['selected_indices'] for v in arms.values() if v['mixed_output']==text)} for j,text in enumerate(outputs)];cid='qualified-noun-'+str(i).zfill(3);key={m:next(o['option_id'] for o in options if o['mixed_output']==v['mixed_output']) for m,v in arms.items()};union={};hids=set();rids=set()
  for m,v in arms.items():
   for index in v['selected_indices']:
    c=t['candidates'][index];sig=enc([c['focus_utf16'],c['target'],c['reading']]);u=union.setdefault(sig,{'focus_utf16':c['focus_utf16'],'source':c['source'],'target':c['target'],'reading':c['reading'],'option_ids':[]})
    if key[m] not in u['option_ids']:u['option_ids'].append(key[m])
    hids.add(c['head_id']);context=c['context_id']
    if context not in witness['contexts']:
     blob=db.execute('select proof from contexts where id=?',(context,)).fetchone()[0];proof=json.loads(zlib.decompress(blob));witness['contexts'][context]={'original_blob_sha256':hashlib.sha256(blob).hexdigest(),'full_parallel_record':proof['full_parallel_record'],'variant':proof['variant'],'all_ranked_variant_ids':[x['id'] for x in proof['all_ranked_variants']],'retained_proof_database':str(r.paths['heads'])}
  for g in d['gates'].values():
   if g['chosen_rule_id']:rids.add(g['chosen_rule_id'])
  for rid in rids:
   if rid in witness['rules']:continue
   rule=next(v for v in lookup['rules'].values() if v['id']==rid);witness['rules'][rid]=rule
   for ids in rule['support_rows'].values():
    for rowid in ids:
     for pid in databyid[rowid]['pair_ids']:witness['training_pairs'][pid]=data['pairs'][pid]
  _,_,ci,ti=t['id'].split('-');conv=conversations[int(ci)];turn=int(ti);assert conv['dialog'][turn]==[0,t['text']]
  cases.append({'case_id':cid,'source_id':t['id'],'known_state':known,'development_control':pick['development_control'],'source':t['text'],'full_prior_dialogue':conv['dialog'][:turn],'native_words_utf16':t['native_words_utf16'],'source_masks':t['source_masks'],'protected_ranges_utf16':t['protected_ranges_utf16'],'options':options,'union_emissions':list(union.values()),'policy':'Native source grammar retained; no target sentence is role/meaning truth. Empty/original gets zero immersion.'});methodkey.append({'case_id':cid,**pick,'methods':key});witness['case_references'][cid]={'selected_head_ids':sorted(hids),'qualifying_rule_ids':sorted(rids),'gate_audit':d['gates']}
 r.write('anonymous-packet.json',{'cases':cases,'method_labels':False,'parallel_references_in_this_file':False,'agent_review_not_human_validation':True});r.write('method-key.json',methodkey);r.write('parallel-witnesses.json',witness);db.close()
if __name__=='__main__':
 r=Run('packet')
 try:main(r);r.finish()
 except BaseException as e:r.finish(repr(e));raise
