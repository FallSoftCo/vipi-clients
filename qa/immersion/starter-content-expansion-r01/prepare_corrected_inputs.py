#!/usr/bin/env python3
import json,hashlib,shutil
from pathlib import Path
W=Path('/home/ai/Development/investigations/vipi-starter-content-expansion-20261109-r01')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 old=W/'native-inputs-r02';out=W/'native-inputs-r03';assert not out.exists()
 assert sha(old/'native-input-manifest.json')=='982c707a8bfbeb9ef11ac0706e7c66845a809554e17e630067621d57bda9b8eb'
 assert sha(W/'candidates-r02/receipt.json')=='cdd61bcfac6f1883c6ca3f4855486925eaaa332cee73949dbcce4e4893d88287'
 manifest=json.loads((old/'native-input-manifest.json').read_text())
 for name,h in manifest['files'].items():assert sha(old/name)==h
 out.mkdir()
 for name in manifest['files']:shutil.copyfile(old/name,out/name)
 for lang in ['ja','sw']:
  p=W/'candidates-r02'/f'starter-{lang}-candidate-manifest.json';meta=json.loads(p.read_text());pack=p.parent/meta['file'];assert sha(pack)==meta['sha256']
  names=manifest['packs'][lang]['candidate'];shutil.copyfile(pack,out/names['pack']);shutil.copyfile(p,out/names['manifest'])
 manifest['files']={name:sha(out/name) for name in manifest['files']}
 manifest['corrected_candidate_parent_manifest_sha256']=sha(old/'native-input-manifest.json');manifest['corrected_candidate_receipt_sha256']=sha(W/'candidates-r02/receipt.json');manifest['correction_scope']='Remove only apple/jobs/school records; no input row, known state, priority or density policy change. Runtime literal correction bound separately.'
 (out/'native-input-manifest.json').write_text(json.dumps(manifest,sort_keys=True,separators=(',',':'))+'\n');print(sha(out/'native-input-manifest.json'))
if __name__=='__main__':main()
