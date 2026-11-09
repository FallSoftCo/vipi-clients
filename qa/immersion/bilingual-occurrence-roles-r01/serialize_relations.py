import hashlib,json
from pathlib import Path
W=Path('/home/ai/Development/investigations/vipi-bilingual-occurrence-roles-20261109-r01');P=Path('/home/ai/Development/investigations/vipi-lexical-relation-provenance-20261109-r01/trace-r01/evidence.json')
b=P.read_bytes();assert hashlib.sha256(b).hexdigest()=='b4561383adff91b0b899b4c613eda0c79bd5d616fe20080d1cf85467fb99fe82';d=json.loads(b);relations=[]
for t in d['compiler_traces']:
 if t['language']=='en' or not t['counterparts_result']:continue
 raw=d['raw_entries'][str(t['source_line'])]
 for r in t['english_resolutions']:
  record={'kind':'direct_english_gloss_candidate','source_language':'en','published_source_spelling':r['word'],'source_pos':r['pos'],'source_entry_resolved':False,'source_sense_id':None,'matching_source_entry_evidence':r['all_entries'],'original_unique_resolver_result':r['compiler_selected_id'],'target_language':t['language'],'target_native_entry_id':t['source_line'],'target_entry':raw['entry'],'target_published_senses':raw['senses'],'target_native_row_sha256':d['selected_entry_hashes'][str(t['source_line'])],'accepted_bare_gloss':t['counterparts_result'][0],'authority':'Retained native published gloss, not occurrence meaning approval','foreign_pivot_allowed':False,'shipping_edge':False}
  record['relation_id']=hashlib.sha256(json.dumps(record,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest();relations.append(record)
out={'trace_sha256':hashlib.sha256(b).hexdigest(),'relations':relations,'scope':'Only already-traced nonEnglish entries accepted by current bare-gloss grammar; all resolver candidates retained; aliases not newly propagated; current packed terms unchanged.'}
p=W/'direct-english-candidates.json'
with p.open('x') as f:json.dump(out,f,ensure_ascii=False,indent=2);f.write('\n')
print(len(relations),hashlib.sha256(p.read_bytes()).hexdigest())
