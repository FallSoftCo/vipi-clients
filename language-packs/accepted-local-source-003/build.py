#!/usr/bin/env python3
"""Reproduce the finite package using only adjacent retained inputs; no runtime writes."""
from pathlib import Path
import importlib.util,argparse,json,hashlib
R=Path(__file__).resolve().parent
def load(name):
 s=importlib.util.spec_from_file_location(name,R/name/'compile.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True);g.add_argument('--output',type=Path);g.add_argument('--verify',type=Path);a=p.parse_args()
e=load('editorial').build()
for f in (R/'bare/inputs/base').iterdir():
 assert f.read_bytes()==e['packs/'+f.name],f.name
out=load('bare').build()
if a.output:
 assert not a.output.exists();a.output.mkdir(parents=True)
 for n,b in out.items():q=a.output/n;q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(b)
else:
 for n,b in out.items():assert (a.verify/n).read_bytes()==b,n
print(json.dumps({'files':len(out),'bytes':sum(map(len,out.values())),'hash_manifest_sha256':hashlib.sha256(out['hash-manifest.json']).hexdigest(),'index_sha256':hashlib.sha256(out['packs/all-pair-source-catalog-001.json']).hexdigest(),'index_bytes':len(out['packs/all-pair-source-catalog-001.json'])}))
