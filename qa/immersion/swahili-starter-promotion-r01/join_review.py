#!/usr/bin/env python3
import argparse,json,hashlib,collections
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('work',type=Path);a=p.parse_args();w=a.work
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
paths=[w/'author-review-r01.json',w/'root-apple-review-r01.json',w/'apple-review-packet-r01/review-packet.json'];author,root,packet=[json.loads(p.read_text()) for p in paths]
assert author['packet_sha256']==root['packet_sha256']==sha(paths[2]);index={(r['id'],r['known_state']):r for r in root['rows']};joined=[]
for r in author['rows']:
 other=index[(r['id'],r['known_state'])];joined.append({'id':r['id'],'known_state':r['known_state'],'author':r,'root':other,'disagreement':r['label']!=other['verdict']})
assert len(joined)==384
counts={}
for state in range(3):
 rows=[r for r in packet['cases'] if r['known_state']==state];counts[state]={'messages':len(rows),'nonempty':sum(bool(r['spans']) for r in rows),'spans':sum(len(r['spans']) for r in rows),'origins':dict(collections.Counter(r['origin'] for r in rows))}
result={'schema':1,'bindings':{str(p):sha(p) for p in paths},'reviewers':'independent agents, not human/native-speaker validation','label_policy':'original labels retained; no majority gold','author_counts':dict(collections.Counter(r['label'] for r in author['rows'])),'root_counts':dict(collections.Counter(r['verdict'] for r in root['rows'])),'mechanics':counts,'disagreements':[r for r in joined if r['disagreement']],'rows':joined}
out=w/'joined-review-r01.json';assert not out.exists();out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(sha(out),result['author_counts'],result['root_counts'],len(result['disagreements']))
