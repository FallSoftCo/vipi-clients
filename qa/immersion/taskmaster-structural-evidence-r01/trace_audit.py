"""Accepted-consumption evidence for the frozen diagnostic stage subset only."""
import importlib.util,json,re
from pathlib import Path
w=Path('/home/ai/Development/investigations/vipi-taskmaster-structural-evidence-20261109-r01');p=Path(__file__).resolve().parents[1]/'apertium-lexical-selection-r01/run.py';spec=importlib.util.spec_from_file_location('stream',p);h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
maps={r['id']:r for r in json.loads((w/'engine/mapping.json').read_text())};rows=[]
for directory in sorted((w/'diagnostics').iterdir()):
 cid=directory.name;m=maps[cid];lex=h.units((directory/'lexical.raw').read_text());stream=['/'.join(u['fields']) for u in lex];pending=None;accepted=[];rejected=[]
 for ln,line in enumerate((directory/'chunk.stderr').read_text().splitlines(),1):
  hit=re.fullmatch(r'apertium-transfer: Rule (\d+) line (\d+) (.*)',line)
  if hit:pending={'rule':int(hit[1]),'rule_xml_line':int(hit[2]),'matched_stream':hit[3],'trace_line':ln}
  take=re.fullmatch(r'num_words_to_consume: (-?\d+)',line)
  if take:
   assert pending is not None,(cid,ln)
   value=int(take[1]);r=dict(pending,consume_trace_line=ln,num_words_to_consume=value);pending=None
   if value==0:rejected.append(r);continue
   hits=[]
   for a in range(len(stream)):
    for b in range(a+1,len(stream)+1):
     if ' '.join(stream[a:b])==r['matched_stream']:hits.append([a,b])
   r['exact_lexical_intervals']=hits;r['source_utf16']=None
   if len(hits)==1:
    a,b=hits[0]
    if value>0:b=min(b,a+value)
    r['accepted_lexical_interval']=[a,b]
    if m['mapped'] and b<=len(m['source_spans']) and all(s is not None for s in m['source_spans'][a:b]):r['source_utf16']=[m['source_spans'][a][0],m['source_spans'][b-1][1]]
   r['mapping_limit']='Exact lexical interval only unless whole-sequence source identity also passes; repeated pattern ambiguity remains null'
   accepted.append(r)
 rows.append({'id':cid,'accepted_consumptions':accepted,'explicit_rejections':rejected,'source_mapping':m['mapped']})
result={'scope':'13 previously flagged or actual LRX-change diagnostic messages; not all200 trace attribution','records':rows,'meaning_approval':False,'generated_output_alignment':False};(w/'trace-audit.json').write_text(json.dumps(result,indent=2)+'\n');print('cases',len(rows),'accepted',sum(len(r['accepted_consumptions']) for r in rows),'uniquelexical',sum(len(t['exact_lexical_intervals'])==1 for r in rows for t in r['accepted_consumptions']),'sourcebound',sum(t['source_utf16'] is not None for r in rows for t in r['accepted_consumptions']))
for r in rows:
 for a in r['accepted_consumptions']:
  if any(s in a['matched_stream'].lower() for s in ['help<','great<','drive<','economy<','manager<','room<','address<']):print(r['id'],a['rule'],a['num_words_to_consume'],a['matched_stream'],a['source_utf16'])
