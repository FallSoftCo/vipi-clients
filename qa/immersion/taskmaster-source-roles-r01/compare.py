from pathlib import Path
import json,hashlib,collections
w=Path('/home/ai/Development/investigations/vipi-taskmaster-source-roles-20261109-r01');p=w.parent/'vipi-target-informed-taskmaster-20261109-r01';load=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
a=load(w/'run-r01/output.json');native={r['id']:r for r in a['cases']};old=load(p/'run-r02/output.json');inputs=load(p/'inputs-200.json');assert len(native)==200
for row,prior in zip(a['cases'],old['cases']):
 assert row['id']==prior['id'] and row['original']==prior['original']
 for new,prev in [('words','source_native_words'),('sentences','source_native_sentences'),('source_masks','source_strict_masks'),('source_overlap_protections','source_overlap_protections')]:assert row[new]==prior[prev],(row['id'],new)
 assert row['source_sha256']==hashlib.sha256(row['original'].encode()).hexdigest()
 for o in row['observations']:assert row['original'].encode('utf-16-le')[o['utf16'][0]*2:o['utf16'][1]*2].decode('utf-16-le')==o['text']
dictionary={str(r['lexeme']['id']):r for r in load(w/'source-dictionary-forms.json')['rows']};protocol=load(Path(__file__).parent/'protocol.json');mapping=protocol['comparison']['mapping'];edges=load(w/'edges-172.json');groups=collections.defaultdict(list)
for r in edges:
 e=r['edge'];row=native[r['id']];obs=[o for o in row['observations'] if o['utf16']==e['source']];d=dictionary[e['source_lexeme']];pos=d['lexeme']['pos']
 status='unassessed_geometry'
 if len(obs)==1:
  tag=obs[0]['raw_tag'];status='unassessed_role' if row['status']!='ready' or tag not in mapping else 'compatible' if pos in mapping[tag] else 'incompatible'
 r.update(dictionary_pos=pos,lexeme_record=d['lexeme'],retained_form_alternatives=d['forms'],observations=obs,comparison=status)
 key=(r['id'],tuple(e['source']),tuple(e['target']));groups[key].append(r)
assert len(groups)==172
scope=[]
for key,rows in groups.items():
 states={r['comparison'] for r in rows};status='compatible' if 'compatible' in states else 'incompatible' if states=={'incompatible'} else 'unassessed'
 scope.append({'id':key[0],'source_utf16':list(key[1]),'target_utf16':list(key[2]),'comparison':status,'edge_alternatives':rows})
indexed={(r['id'],tuple(r['source_utf16']),tuple(r['target_utf16'])):r for r in scope}
keys={(r['id'],r['label']):r['method'] for r in load(p/'packet/method-key.json')};review={(r['id'],keys[r['id'],r['option']]):r for r in load(p/'author-review-r01.json')['options']};selected=[]
for method,rows in [('A',old['baseline']),('B',old['cases'])]:
 for row in rows:
  labels={json.dumps(u['span'],sort_keys=True):u for u in review[row['id'],method]['units']}
  for span in row.get('aligned_spans_after_strict_snapshot_veto',[]):
   match=indexed.get((row['id'],tuple(span['source_utf16']),tuple(span['target_utf16'])));state=match['comparison'] if match else 'outside_graph'
   selected.append({'id':row['id'],'method':method,'span':span,'comparison':state,'frozen_author':labels[json.dumps(span,sort_keys=True)]})
summary={'messages':200,'native_words':sum(len(r['words']) for r in a['cases']),'statuses':dict(collections.Counter(r['status'] for r in a['cases'])),'lexeme_edge_records':len(edges),'form_term_proofs':sum(r['proof_count'] for r in edges),'unique_scope_edges':len(scope),'lexeme_comparison':dict(collections.Counter(r['comparison'] for r in edges)),'scope_comparison':dict(collections.Counter(r['comparison'] for r in scope)),'selected_by_method':{m:dict(collections.Counter(r['comparison'] for r in selected if r['method']==m)) for m in ['A','B']},'incompatible_selected_frozen_labels':{m:dict(collections.Counter(r['frozen_author']['label'] for r in selected if r['method']==m and r['comparison']=='incompatible')) for m in ['A','B']},'interpretation':'Read-only edge inventory, not re-selection, no budget refilling or new predictions; unknown remains unassessed','geometry_and_protection_parity':True}
result={'summary':summary,'scope_edges':scope,'selected_spans':selected,'inputs':[{'path':str(f),'sha256':sha(f)} for f in [w/'run-r01/output.json',w/'source-dictionary-forms.json',w/'edges-172.json',p/'run-r02/output.json',p/'author-review-r01.json',Path(__file__).parent/'protocol.json']]}
(w/'comparison.json').write_text(json.dumps(result,indent=2)+'\n');(w/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
print('INCOMPATIBLE SELECTED B')
for r in selected:
 if r['method']=='B' and r['comparison']=='incompatible':print(r['id'],r['span'],r['frozen_author']['label'])
