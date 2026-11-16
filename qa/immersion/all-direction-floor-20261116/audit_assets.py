"""Static inventory only: never equate substrings with native emissions."""
import json,unicodedata
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).parent
fixture=json.loads((HERE/'fixtures.json').read_text())
rows=[];pairs=[]
for source in fixture['languages']:
 for target in fixture['languages']:
  if source==target:continue
  manifest=json.loads((ROOT/f'data/immersion/source-frames-{source}-{target}-catalog.json').read_text())
  pack=json.loads((ROOT/'data/immersion'/manifest['file']).read_text())
  bad=[p['id'] for p in pack['patterns'] if target in ['ar','zh','ja','ko'] and (not p['reading'] or any(unicodedata.category(c).startswith('L') and 'LATIN' not in unicodedata.name(c,'') for c in p['reading']))]
  pairs.append(dict(pair=f'{source}-{target}',patterns=len(pack['patterns']),non_latin_reading_issues=bad))
  for case in fixture['cases']:
   if case['source_language']!=source or case['target_language']!=target:continue
   matches=[dict(pattern_id=p['id'],source=p['source'],target=p['target'],reading=p['reading'],context=v['context']) for p in pack['patterns'] for v in p['variants'] if v['context'] in case['original']]
   rows.append(dict(id=case['id'],literal_context_candidates=matches))
result=dict(scope='Static literal substring inventory. Ignores native boundaries, detector, baseline provider, density, masks, and normalized identity. Not emission or linguistic accuracy evidence.',directions=len(pairs),pairs=pairs,rows=rows,rows_without_literal_context=sum(not r['literal_context_candidates'] for r in rows))
(HERE/'asset-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ['pairs','rows']}));print('Reading issue patterns',sum(len(p['non_latin_reading_issues']) for p in pairs))
