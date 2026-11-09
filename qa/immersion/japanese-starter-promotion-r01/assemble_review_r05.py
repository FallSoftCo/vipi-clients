#!/usr/bin/env python3
"""Lossless compact review view; no semantic labels or case reselection."""
from pathlib import Path
import argparse,hashlib,json
p=argparse.ArgumentParser();p.add_argument('raw',type=Path);p.add_argument('out',type=Path);a=p.parse_args();assert not a.out.exists()
b=a.raw.read_bytes();raw=json.loads(b);assert raw['complete'] and len(raw['cases'])==384
rows=raw['cases'];assert all(r['status'].lower()!='stale' for r in rows);assert len({(r['id'],r['known_state']) for r in rows})==384
out={'schema':1,'platform':raw['platform'],'raw_sha256':hashlib.sha256(b).hexdigest(),'activation':raw['activation'],'default_provider_path':raw.get('default_provider_path',False),'review_kind':'independent agent review; diagnostic controls, not population coverage','cases':[{k:r.get(k) for k in ['id','stratum','original','known_state','known_ids','density','status','origin','mixed','full_reference','spans','starter_spans','trace','recognitions']} for r in rows]}
a.out.write_text(json.dumps(out,ensure_ascii=False,separators=(',',':'))+'\n');print(json.dumps({'path':str(a.out),'sha256':hashlib.sha256(a.out.read_bytes()).hexdigest(),'rows':len(rows),'bytes':a.out.stat().st_size}))
