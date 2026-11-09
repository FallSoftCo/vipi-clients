"""Read-only source-stage assessment; never relax bilingual sequence mapping."""
import collections,hashlib,json,re
from pathlib import Path
w=Path('/home/ai/Development/investigations/vipi-taskmaster-structural-evidence-20261109-r01');load=lambda p:json.loads(p.read_text());x=load(w/'comparison/comparison.json');maps={r['id']:r for r in load(w/'engine/mapping.json')};tags={'n':'noun','np':'proper_name','vblex':'verb','vaux':'verb','vbser':'verb','vbhaver':'verb','vbmod':'verb','adj':'adj','adv':'adv','ij':'intj','num':'num','prn':'pron','det':'det','pr':'prep','cnjcoo':'conj','cnjsub':'conj'};rows=[]
for e in x['edges']:
 m=maps[e['id']];ix=[i for i,s in enumerate(m['source_spans']) if s==e['source_utf16']];r={k:e[k] for k in ['id','source_utf16','target_utf16']};r['bilingual_mapping_unchanged']=e['status']
 if len(ix)!=1:r['source_only_status']='unassessed_geometry'
 else:
  a=m['source_analyses'][ix[0]];t=re.findall(r'<([^>]+)>',a);pos=tags.get(t[0]) if t else None;r.update(analysis=a,source_pos=pos,dictionary_pos=sorted({a['dictionary_pos'] for a in e['original_edge_alternatives']}));r['source_only_status']='unassessed_role' if pos is None or a.startswith(('*','@','#')) or '+' in a else 'compatible' if pos in r['dictionary_pos'] else 'incompatible'
 rows.append(r)
idx={(r['id'],tuple(r['source_utf16']),tuple(r['target_utf16'])):r for r in rows};selected=[]
for old in x['selected']:
 r=idx.get((old['id'],tuple(old['span']['source_utf16']),tuple(old['span']['target_utf16'])));new=dict(old);new['source_stage_only']=r;selected.append(new)
summary={'scope_edges':dict(collections.Counter(r['source_only_status'] for r in rows)),'selected':{},'incompatible_labels':{}}
for m in ['A','B']:
 ss=[r for r in selected if r['method']==m];summary['selected'][m]=dict(collections.Counter(r['source_stage_only']['source_only_status'] if r['source_stage_only'] else 'outside_graph' for r in ss));summary['incompatible_labels'][m]=dict(collections.Counter(r['frozen_author']['label'] for r in ss if r['source_stage_only'] and r['source_stage_only']['source_only_status']=='incompatible'))
result={'scope':'source-stage exact focus geometry only; bilingual mapping abstentions unchanged','summary':summary,'edges':rows,'selected':selected};(w/'source-stage-audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(summary,indent=2))
for r in selected:
 if r['method']=='B' and r['source_stage_only'] and r['source_stage_only']['source_only_status']=='incompatible':print(r['span']['source'],r['span']['target'],r['frozen_author']['label'],r['source_stage_only']['analysis'])
