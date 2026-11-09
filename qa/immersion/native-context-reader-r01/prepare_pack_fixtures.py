#!/usr/bin/env python3
"""PREPARED ONLY. Deterministic synthetic rule-context parity fixture, no semantic labels."""
import argparse,sqlite3,json,hashlib,pathlib,unicodedata,re
p=argparse.ArgumentParser();p.add_argument('pack',type=pathlib.Path);p.add_argument('output',type=pathlib.Path);a=p.parse_args()
assert unicodedata.unidata_version=='15.0.0'
assert hashlib.sha256(a.pack.read_bytes()).hexdigest()=='cd7a8667ff0df53610ef19aa585398e24470716dd23af6d640b7c77dbc3badb4'
db=sqlite3.connect(a.pack.as_uri()+'?mode=ro&immutable=1',uri=True);db.row_factory=sqlite3.Row
rules=[dict(r) for r in db.execute('select * from rules order by id')]
for r in rules:r['tokens']=json.loads(r['tokens_json']);r['heads']=[x[0] for x in db.execute('select head_id from rule_heads where rule_id=? order by head_id',(r['id'],))]
assert len(rules)==1157 and sum(not r['heads'] for r in rules)==23
rows=[];token=re.compile(r"[^\W_]+(?:['’][^\W_]+)*|[^\w\s]",re.UNICODE)
norm=lambda s:' '.join(unicodedata.normalize('NFC',s).casefold().split())
for r in rules:
 text=' '.join(r['tokens']);ts=list(token.finditer(text));values=[norm(t.group()) for t in ts]
 # No silent fixture repair if normalized tokens do not roundtrip.
 if values!=r['tokens']:
  rows.append({'rule_id':r['id'],'source':text,'roundtrip':False,'expected_abstention':'retokenization_changed'});continue
 ranges=[[len(text[:t.start()].encode('utf-16-le'))//2,len(t.group().encode('utf-16-le'))//2] for t in ts];focus=r['focus_offset'];matches=[]
 for q in rules:
  if q['source_key']!=r['source_key']:continue
  start=focus-q['focus_offset'];end=start+q['length']
  if start<0 or end>len(values) or values[start:end]!=q['tokens'] or any(not any(c.isalpha() for c in v) for v in values[start:end]):continue
  matches.append(((-q['length'],-(q['ratio'] if q['ratio'] is not None else float('inf')),-q['winner_components'],-q['winner_weight'],start,q['id']),q,start,end))
 matches.sort(key=lambda x:x[0]);chosen=matches[0] if matches else None
 rows.append({'rule_id':r['id'],'source':text,'roundtrip':True,'ranges':ranges,'focus':ranges[focus],'source_keys':[r['source_key']], 'winner':None if chosen is None else {'id':chosen[1]['id'],'head_ids':chosen[1]['heads'],'target':chosen[1]['target'],'context_range':[ranges[chosen[2]][0],sum(ranges[chosen[3]-1])-ranges[chosen[2]][0]]}})
out={'schema':'vipi.frozen-context-pack.synthetic-rule-fixtures.r01','pack_sha256':hashlib.sha256(a.pack.read_bytes()).hexdigest(),'scope':'Synthetic exact rule contexts; supplied scalar geometry must separately match native geometry for any native admission. No semantic acceptance or source role/mask integration. All no-head winners retained.','rows':rows}
raw=json.dumps(out,ensure_ascii=False,separators=(',',':')).encode();assert len(raw)<=4*1024*1024
with a.output.open('xb') as f:f.write(raw)
print(json.dumps({'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'rows':len(rows)}))
