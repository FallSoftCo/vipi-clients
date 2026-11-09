#!/usr/bin/env python3
from pathlib import Path
import argparse,hashlib,json
R=Path(__file__).resolve().parents[3]
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output-dir',type=Path,required=True);a=ap.parse_args()
 source=R/'qa/immersion/coverage_ceiling_experiment/reviewed-source-unit-native-candidate-r03.json';concepts=source.with_name('content-expansion-candidate-r01.json');raw=source.read_bytes();cr=concepts.read_bytes()
 assert sha(raw)=='52199a35fb4d18d5b1f1ee9ebd4c3ddf3d081ce2c44a01bac3daecc46ee08c4d';assert sha(cr)=='5264106ac021932f97350767a792a53e74cdac2fed4242997c9e771a683508a4'
 original=json.loads(raw);by={e['id']:e for e in json.loads(cr)['pairs']['en-sw']['entries']};rows=original['pairs']['en-sw']['entries'];assert len(rows)==107;entries=[];removed=[]
 for e in rows:
  assert (e['source'],e['target'])==(by[e['id']]['source'],by[e['id']]['target'])
  if e['id']=='word-en-sw-winter':removed.append(e);continue
  x={k:e[k] for k in ['id','source','target','category','pos','train_rank','source_tokens']};x.update({k:e[k] for k in ['guard','following'] if k in e});x.update(concept_id=by[e['id']]['concept_id'],record_sha256=sha(json.dumps(e,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()));entries.append(x)
 assert len(removed)==1 and len(entries)==106
 pack={'schema':'vipi-source-starter-1','version':'starter-en-sw-001','source':'en','target':'sw','entries':entries,'source_context_sets':original['source_context_sets'],'source_pack_sha256':sha(raw),'concept_pack_sha256':sha(cr),'licenses':{'sw':original['licenses']['sw']},'selection':'one budget-fitting unit, content-first, TRAIN-rank, longer-source, source-offset','withheld_original_entry_ids':[e['id'] for e in removed],'reading_policy':'Latin-script target; no synthetic romanization'}
 data=(json.dumps(pack,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode();manifest={'schema':'vipi-source-starter-manifest-1','file':'starter-en-sw-001.json','sha256':sha(data),'bytes':len(data),'version':pack['version'],'entries':len(entries)}
 a.output_dir.mkdir(parents=True,exist_ok=False);(a.output_dir/manifest['file']).write_bytes(data);(a.output_dir/'starter-sw-catalog.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(manifest))
if __name__=='__main__':main()
