#!/usr/bin/env python3
"""All frozen rows; source/mixed options separate from lookup/reference evidence."""
import argparse,json,hashlib
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('raw',type=Path);p.add_argument('out',type=Path);a=p.parse_args();assert not a.out.exists();a.out.mkdir()
b=a.raw.read_bytes();d=json.loads(b);rows=d['cases'];assert d['complete'] and len(rows)==384 and d['japanese_parity_rows']==384
assert len({(r['id'],r['known_state']) for r in rows})==384
assert all(r['status'].lower()!='stale' and r['translation_calls']==0 for r in rows)
base={'schema':1,'raw_sha256':hashlib.sha256(b).hexdigest(),'platform':d['platform'],'activation':d['activation'],'default_provider_path':d['default_provider_path'],'interpretation':'Independent agent diagnostic review; original128 x 3known states; empty zero usefulness; no population claim.'}
for name,keys in [('review-packet.json',['id','stratum','original','known_state','known_ids','density','status','origin','mixed','spans']),('parallel-evidence.json',['id','known_state','full_reference','starter_spans','trace','recognitions'])]:
 out=a.out/name;out.write_text(json.dumps({**base,'cases':[{k:r.get(k) for k in keys} for r in rows]},ensure_ascii=False,separators=(',',':'))+'\n');print(name,hashlib.sha256(out.read_bytes()).hexdigest(),out.stat().st_size)
