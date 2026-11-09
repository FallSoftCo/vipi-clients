"""Predeclared review strata and exact full-message paired evidence."""
import collections,gzip,hashlib,json,sqlite3,unicodedata,zlib
from pathlib import Path
KNOWN=['all_function','all_function_global300']
QUOTAS=[('loss',4),('empty_gain',6),('nonempty_change',6)]
def enc(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def fingerprint(text):return hashlib.sha256(('en\0'+' '.join(unicodedata.normalize('NFC',text).casefold().split())).encode()).hexdigest()
class Selection:
 def __init__(self,plan):
  self.plan=plan;ex=json.loads(Path(plan['inputs']['review_exclusions']['path']).read_text());self.excluded=set(ex['hashes']);self.ids=set(ex['source_ids']);self.pool=collections.defaultdict(list);self.counts=collections.Counter()
 def consider(self,row):
  cs=row['candidates']
  for known in KNOWN:
   arms=row['decisions'][known];a=[cs[i] for i in arms['baseline']['selected_indices']];b=[cs[i] for i in arms['experimental']['selected_indices']]
   signature=lambda selected:sorted(enc([c['focus_utf16'],c['target'],c['reading']]) for c in selected)
   changed=signature(a)!=signature(b) or arms['baseline']['mixed_output']!=arms['experimental']['mixed_output'];self.counts[known+':changed']+=changed
   if not changed:continue
   stratum='loss' if sum(c['cost'] for c in b)<sum(c['cost'] for c in a) else 'empty_gain' if not a and b else 'nonempty_change'
   self.counts[known+':'+stratum]+=1
   if row['id'] in self.ids or fingerprint(row['text']) in self.excluded:self.counts['exposure_excluded']+=1;continue
   rank=hashlib.sha256(('source-name-scope-r01|'+stratum+'|'+known+'|'+row['id']).encode()).hexdigest()
   pool=self.pool[stratum,known];pool.append((rank,row['id']));pool.sort();del pool[34:]
 def freeze(self):
  selected=[];seen=set();shortages=[]
  for stratum,quota in QUOTAS:
   for known in KNOWN:
    n=0
    for rank,ident in self.pool[stratum,known]:
     if ident in seen:continue
     selected.append({'source_id':ident,'known':known,'stratum':stratum,'sampling_hash':rank});seen.add(ident);n+=1
     if n==quota:break
    if n<quota:shortages.append({'stratum':stratum,'known':known,'quota':quota,'selected':n})
  assert len(selected)<=32
  return {'production':False,'selected':selected,'shortages':shortages,'counts':dict(self.counts),'policy':self.plan['review'],'no_backfill':True}

def packet(r):
 project=r.prior('project');catalog=r.prior('catalog');selection=json.loads((project/'review-selection-freeze.json').read_text());development=r.plan['development_source_ids'];wanted=set(development)|{p['source_id'] for p in selection['selected']};rows={}
 with gzip.open(project/'decisions.jsonl.gz','rt') as f:
  for line in f:
   row=json.loads(line)
   if row['id'] in wanted:rows[row['id']]=row
 assert set(rows)==wanted
 conversations=json.loads(r.paths['source_context'].read_text());db=sqlite3.connect(r.paths['heads'].as_uri()+'?mode=ro&immutable=1',uri=True);db.execute('PRAGMA cache_size=-8192');catalogdb=sqlite3.connect((catalog/'catalog.sqlite').as_uri()+'?mode=ro&immutable=1',uri=True)
 r.stack.callback(db.close);r.stack.callback(catalogdb.close);witnesses={};heads={}
 def case(pick):
  row=rows[pick['source_id']];_,_,ci,ti=row['id'].split('-');conv=conversations[int(ci)];turn=int(ti);assert conv['dialog'][turn]==[0,row['text']]
  arms=row['decisions'][pick['known']];union={}
  for arm,data in arms.items():
   for i in data['selected_indices']:
    c=row['candidates'][i];key=enc([c['focus_utf16'],c['target'],c['reading']]);u=union.setdefault(key,{'source':c['source'],'focus_utf16':c['focus_utf16'],'target':c['target'],'reading':c['reading'],'arms':[],'candidate_indices':[]});u['arms'].append(arm)
    if i not in u['candidate_indices']:u['candidate_indices'].append(i)
    hid=c['head_id'];cid=c['context_id']
    if hid not in heads:
     blob=db.execute('SELECT proof FROM contexts WHERE id=?',(cid,)).fetchone()[0];proof=json.loads(zlib.decompress(blob));head=next(h for h in proof['result']['heads'] if cid+':'+h['head_id']==hid)
     audit=json.loads(catalogdb.execute('SELECT audit FROM heads WHERE id=?',(hid,)).fetchone()[0]);heads[hid]={'original_head':head,'experimental_audit':audit,'context_id':cid}
     if cid not in witnesses:
      pair=proof['full_parallel_record'];witnesses[cid]={'original_blob_sha256':hashlib.sha256(blob).hexdigest(),'pair_id':pair['pair_id'],'source':pair['source'],'target':pair['target'],'variant':proof['variant'],'all_ranked_variant_ids':[v['id'] for v in proof['all_ranked_variants']],'original_proof_database':str(r.paths['heads'])}
  return {**pick,'source':row['text'],'review_only_preceding_context':conv['dialog'][:turn],'native_words_utf16':row['native_words_utf16'],'source_masks':row['source_masks'],'protected_ranges_utf16':row['protected_ranges_utf16'],'candidates':row['candidates'],'baseline_candidate_count':row['baseline_candidate_count'],'competition_removed_baseline_indices':row['competition_removed_baseline_indices'],'arms':arms,'review_union':list(union.values()),'geometry_rejections':row['geometry_rejections'],'experimental_geometry_rejections':row['experimental_geometry_rejections']}
 cases=[case(dict(p,review_id=f'name-scope-{i:03d}',development_control=False)) for i,p in enumerate(selection['selected'],1)]
 controls=[case({'source_id':ident,'known':known,'development_control':True,'review_id':f'development-{i:02d}-{known}'}) for i,ident in enumerate(development,1) for known in KNOWN]
 output={'production':False,'semantic_labels_present':False,'selection_sha256':r.adapter.sha(project/'review-selection-freeze.json'),'cases':cases,'development_controls':controls,'witnesses':witnesses,'selected_head_evidence':heads,'limits':'Every union emission and both full outputs require review. Development controls already exposed; sampled changes are diagnostic, not population accuracy. Unselected alternatives retain exact catalog/original-proof references; no reranking.'}
 assert len(enc(output).encode())<24*1024**2,'packet quota exceeded; no alternative truncation'
 r.write('review-packet.json',output);r.receipt.update(cases=len(cases),development_controls=len(controls),witnesses=len(witnesses))
