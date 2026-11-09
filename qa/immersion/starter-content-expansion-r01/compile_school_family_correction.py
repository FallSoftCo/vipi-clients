#!/usr/bin/env python3
"""Additive plural-family withholding; do not alter the running r02 inputs."""
import json,hashlib
from pathlib import Path
W=Path('/home/ai/Development/investigations/vipi-starter-content-expansion-20261109-r01')
def enc(x):return (json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 parent=W/'candidates-r02';assert sha(parent/'receipt.json')=='cdd61bcfac6f1883c6ca3f4855486925eaaa332cee73949dbcce4e4893d88287'
 out=W/'candidates-r03';assert not out.exists();out.mkdir();summary={};withheld=[]
 for lang,old,new,total,pin in [('ja','004','005',189,'b36deb4c78a4c4122a7c4e6aa1b8708c3f6e5ba52c3eb660cef0a06c26e3a9a6'),('sw','003','004',213,'68e2a1b651eee367421ce14ff1293e1d7d67d81fa963c0510a978eb9862cb20d')]:
  p=parent/f'starter-en-{lang}-{old}.json';assert sha(p)==pin;pack=json.loads(p.read_text());id=f'word-en-{lang}-schools';before=pack['entries'];removed=[e for e in before if e['id']==id];assert len(removed)==1 and removed[0]['concept_id']=='schools';withheld+=removed
  pack['entries']=[e for e in before if e['id']!=id];assert len(pack['entries'])==total
  active=json.loads((W/'native-inputs-r02'/f'current-{lang}.json').read_text());after={e['id']:e for e in pack['entries']};assert all(after[e['id']]==e for e in active['entries']);assert f'word-en-{lang}-job' in after
  pack['version']=f'starter-en-{lang}-{new}';pack['qualification_status']='school_family_correction_awaiting_default_route_qualification';pack['withheld_original_entry_ids']=sorted(set(pack['withheld_original_entry_ids'])|{id});pack['correction_parent_sha256']=pin;pack['activation']=False
  file=out/(pack['version']+'.json');file.write_bytes(enc(pack));manifest={'schema':'vipi-source-starter-manifest-1','version':pack['version'],'file':file.name,'entries':total,'bytes':file.stat().st_size,'sha256':sha(file)};(out/f'starter-{lang}-candidate-manifest.json').write_bytes(enc(manifest))
  proofs=json.loads((parent/f'proofs-{lang}.json').read_text());kept=[x for x in proofs if x['entry_id']!=id];assert len(proofs)-len(kept)==1;assert all(x['record_sha256']==after[x['entry_id']]['record_sha256'] for x in kept);(out/f'proofs-{lang}.json').write_bytes(enc(kept));summary[lang]={'entries':total,'active_entries_preserved':len(active['entries']),'removed':id,'all_other_entry_objects_and_order_unchanged':True,'parent_pack_sha256':pin}
 (out/'withheld-plural-records.json').write_bytes(enc({'records':withheld,'reason':'Root corrected omission: plural schools shares the institutional sense and unresolved collective ambiguity of school. No new semantic gold label inferred.'}))
 receipt={'schema':1,'code_sha256':sha(Path(__file__)),'parent_receipt_sha256':sha(parent/'receipt.json'),'summary':summary,'root_instruction':'Let r02 finish; withhold school and schools concept forms, preserving all other records. If no schools recognition in retained inputs/traces, no extra full grid; qualify final bundle/default route with plural controls.','files':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in out.iterdir()},'native_execution':False,'activation':False};(out/'receipt.json').write_bytes(enc(receipt));print(sha(out/'receipt.json'))
if __name__=='__main__':main()
