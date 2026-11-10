from pathlib import Path
import json,hashlib,shutil
W=Path('/home/ai/Development/investigations/vipi-source-context-frames-20261109-r01');sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 out=W/'cases-r02';assert not out.exists();out.mkdir();parent=W/'cases-r01/sources.json';d=json.loads(parent.read_text());n=len(d['cases'])
 for pair in ['en-ja','en-sw']:
  for i,source in enumerate(['@my dog is asleep.','#bank account is unavailable.','@phone charger arrived.']):d['cases'].append({'id':f'context-literal-{i+1:02d}','pair':pair,'source':source,'stratum':'protected_context_outside_focus','exposure':'Root code-review adversarial diagnostic, pre-output; not fresh corpus.','pattern_ids':[],'record_bindings':[]})
 assert len(d['cases'])==160;(out/'sources.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n');(out/'receipt.json').write_text(json.dumps({'parent_sha256':sha(parent),'original_cases_unchanged':d['cases'][:n]==json.loads(parent.read_text())['cases'],'added_source_pair_cases':6,'source_sha256':sha(out/'sources.json'),'basis':'Full-context literal protection found missing in preliminary adapter review; original frozen case receipt retained.'},indent=2)+'\n')
 dest=W/'native-inputs-r02';assert not dest.exists();shutil.copytree(W/'native-inputs-r01',dest);shutil.copyfile(out/'sources.json',dest/'cases.json');m=json.loads((dest/'manifest.json').read_text());m['files']['cases.json']=sha(dest/'cases.json');m['parent_manifest_sha256']=sha(W/'native-inputs-r01/manifest.json');m['source_pair_cases']=160;m['expected_comparison_rows']=656;(dest/'manifest.json').write_text(json.dumps(m,indent=2)+'\n');print(sha(dest/'manifest.json'))
if __name__=='__main__':main()
