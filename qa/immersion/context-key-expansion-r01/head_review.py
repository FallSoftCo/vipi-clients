#!/usr/bin/env python3
"""Frozen changed-message strata; no semantic labels or output-based reselection."""
import collections,gzip,hashlib,json,sqlite3,zlib
from pathlib import Path
KNOWN=['all_function','all_function_global300']
STRATA=['empty_gain','depth_loss','new_long_context','other_change']
def enc(x):return json.dumps(x,ensure_ascii=False,separators=(',',':'),sort_keys=True)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
class Selection:
 def __init__(self,plan,hashes):
  self.plan=plan;self.excluded=set(hashes);self.pools=collections.defaultdict(list);self.counts=collections.Counter()
 def consider(self,row):
  import unicodedata
  normalized=' '.join(unicodedata.normalize('NFC',row['text']).casefold().split())
  excluded=hashlib.sha256(('en\0'+normalized).encode()).hexdigest() in self.excluded
  for known in KNOWN:
   by=row['decisions'][known];candidates=row['candidates']
   a=[candidates[i] for i in by['fixed']['selected_indices']];b=[candidates[i] for i in by['expanded']['selected_indices']]
   outputkey=lambda selected:sorted(enc([c['focus_utf16'],c['target'],c['reading']]) for c in selected)
   changed=outputkey(a)!=outputkey(b) or by['fixed']['mixed_output']!=by['expanded']['mixed_output']
   self.counts[known+':changed']+=changed;self.counts[known+':unchanged']+=not changed
   self.counts[known+':both_empty']+=not a and not b
   if not changed:continue
   if not a and b:stratum='empty_gain'
   elif sum(c['cost'] for c in b)<sum(c['cost'] for c in a):stratum='depth_loss'
   elif any(not c['fixed'] and 4<=c['context_native_cost']<=8 for c in b):stratum='new_long_context'
   else:stratum='other_change'
   self.counts[stratum+'|'+known]+=1
   if excluded:self.counts['excluded_review_exposure']+=1;continue
   rank=hashlib.sha256(('|'.join([self.plan['review']['seed'],stratum,known,row['id']])).encode()).hexdigest()
   pool=self.pools[stratum,known];pool.append((rank,row['id']));pool.sort();del pool[34:]
 def freeze(self):
  selected=[];seen=set();shortages=[]
  for stratum in STRATA:
   for known in KNOWN:
    picked=0
    for rank,ident in self.pools[stratum,known]:
     if ident in seen:continue
     seen.add(ident);selected.append({'source_id':ident,'known':known,'stratum':stratum,'sampling_hash':rank});picked+=1
     if picked==4:break
    if picked<4:shortages.append({'stratum':stratum,'known':known,'selected':picked,'quota':4})
  assert len(selected)<=32
  return {'production':False,'semantic_labels_present':False,'selected':selected,'shortages':shortages,'counts':dict(self.counts),'policy':self.plan['review'],'exclusion_sha256':self.plan['inputs']['exclusions']['sha256'],'sampling_limit':'Reused TRAIN diagnostic; exposure exclusions incomplete; no accuracy estimate.'}

def packet(run,project_dir,heads_dir):
 selection=json.loads((project_dir/'review-selection-freeze.json').read_text());wanted={x['source_id']:x for x in selection['selected']};rows={}
 with gzip.open(project_dir/'decisions.jsonl.gz','rt') as f:
  for line in f:
   row=json.loads(line)
   if row['id'] in wanted:rows[row['id']]=row
 assert set(rows)==set(wanted)
 conversations=json.loads(run.paths['source_context'].read_text())
 db=sqlite3.connect((heads_dir/'heads.sqlite').as_uri()+'?mode=ro&immutable=1',uri=True);db.execute('PRAGMA cache_size=-8192')
 cases=[];proofs={}
 try:
  for ordinal,pick in enumerate(selection['selected'],1):
   row=rows[pick['source_id']];_,_,ci,ti=row['id'].split('-');conv=conversations[int(ci)];turn=int(ti)
   assert conv['context_dataset']=='convai2';speaker,text=conv['dialog'][turn];assert speaker==0 and text==row['text']
   known=pick['known'];arms=row['decisions'][known];union={}
   for arm,data in arms.items():
    for i in data['selected_indices']:
     c=row['candidates'][i];key=enc([c['focus_utf16'],c['target'],c['reading']])
     u=union.setdefault(key,{'focus_utf16':c['focus_utf16'],'source':c['source'],'target':c['target'],'reading':c['reading'],'arms':[],'candidate_indices':[]});u['arms'].append(arm)
     if i not in u['candidate_indices']:u['candidate_indices'].append(i)
   # All recognized candidate contexts, including rejected ones, retain full proofs once.
   for c in row['candidates']:
    cid=c['context_id']
    if cid not in proofs:
     result=db.execute('SELECT proof FROM contexts WHERE id=?',(cid,)).fetchone();assert result
     proofs[cid]=json.loads(zlib.decompress(result[0]))
   cases.append({'review_id':f'context-head-{ordinal:03d}',**pick,'source':row['text'],'review_only_preceding_context':conv['dialog'][:turn],'native_words_utf16':row['native_words_utf16'],'source_masks':row['source_masks'],'protected_ranges_utf16':row['protected_ranges_utf16'],'candidates':row['candidates'],'geometry_rejections':row['geometry_rejections'],'arms':arms,'review_union':list(union.values())})
  packet={'schema':'vipi.context-head-comparison.review.r01','production':False,'semantic_labels_present':False,'selection_sha256':sha(project_dir/'review-selection-freeze.json'),'decisions_sha256':sha(project_dir/'decisions.jsonl.gz'),'source_context_sha256':run.plan['inputs']['source_context']['sha256'],'cases':cases,'context_proofs':proofs,'limits':'Review every union emission and both complete outputs, including empty/lost content; unchanged scopes are not preapproved. No majority gold or population accuracy.'}
  data=(enc(packet)+'\n').encode();assert len(data)<=24*1024**2,'packet exceeds reserved proof budget; no truncation'
  run.guard(len(data)+1024**2)
  with (run.out/'review-packet.json').open('xb') as f:f.write(data)
  run.receipt.update(cases=len(cases),unique_context_proofs=len(proofs),packet_sha256=sha(run.out/'review-packet.json'))
 finally:db.close()
