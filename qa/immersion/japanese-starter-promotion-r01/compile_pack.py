#!/usr/bin/env python3
"""Reconstruct the approved winter-withheld pack; never touches runtime assets."""
from pathlib import Path
import argparse,hashlib,json
Q=Path(__file__).resolve().parent
sha=lambda b:hashlib.sha256(b).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output-dir',type=Path,required=True);args=ap.parse_args()
 raw=(Q/'starter-en-ja-001.json').read_bytes();assert sha(raw)=='44516f6b5bd289cb31cd3e611e8b0943b763a438615a0e357504dc69b735ab9d'
 policy=json.loads((Q/'correction-protocol-r05.json').read_text());pack=json.loads(raw);removed=policy['removed_entry'];assert sum(e==removed for e in pack['entries'])==1
 pack['entries']=[e for e in pack['entries'] if e!=removed];pack['version']='starter-en-ja-002'
 data=(json.dumps(pack,ensure_ascii=False,indent=2)+'\n').encode();assert sha(data)==policy['new45_sha256']
 manifest={'schema':'vipi-source-starter-manifest-1','file':'starter-en-ja-002.json','sha256':sha(data),'bytes':len(data),'version':pack['version'],'entries':len(pack['entries'])}
 args.output_dir.mkdir(parents=True,exist_ok=False);(args.output_dir/manifest['file']).write_bytes(data);(args.output_dir/'starter-catalog.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(manifest))
if __name__=='__main__':main()
