from pathlib import Path
import json,hashlib,shutil
W=Path('/home/ai/Development/investigations/vipi-source-context-frames-20261109-r01');R=Path(__file__).resolve().parents[3];old=Path('/home/ai/Development/investigations/vipi-starter-content-expansion-20261109-r01/native-inputs-r03');sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 out=W/'native-inputs-r01';assert not out.exists();out.mkdir();spec={};ids=[];ph={}
 for lang,fn,mn in [('ja','starter-en-ja-005.json','starter-catalog.json'),('sw','starter-en-sw-004.json','starter-sw-catalog.json')]:
  for p in [R/'data/immersion'/fn,R/'data/immersion'/mn,W/'preparation-r01'/('patterns-en-'+lang+'.json')]:shutil.copyfile(p,out/p.name)
  patterns=json.loads((out/('patterns-en-'+lang+'.json')).read_text());ids += [p['id'] for p in patterns['patterns']];ph['en-'+lang]=sha(out/('patterns-en-'+lang+'.json'));spec[lang]={'pack':fn,'manifest':mn,'patterns':'patterns-en-'+lang+'.json'}
 perm={'schema':1,'purpose':'test_only_source_permission_proposal','runtime_enabled':False,'seed_permissions_unchanged':True,'pack_sha256':ph,'pattern_ids':sorted(ids),'authority':'Root-authorized bounded source-only qualification; no semantic acceptance or promotion.'};(out/'permission-proposal.json').write_text(json.dumps(perm,sort_keys=True,separators=(',',':'))+'\n')
 shutil.copyfile(W/'cases-r01/sources.json',out/'cases.json');previous=json.loads((old/'comparison-inputs.json').read_text());baseline={'pairs':{k:[r for r in v if r['id'].startswith('retained128/')] for k,v in previous['pairs'].items()},'states':previous['states']};assert all(len(v)==128 for v in baseline['pairs'].values());(out/'baseline-cases.json').write_text(json.dumps(baseline,ensure_ascii=False,separators=(',',':'))+'\n')
 manifest={'schema':1,'packs':spec,'files':{p.name:sha(p) for p in out.iterdir()},'max_output_bytes':32*1024**2,'deadline_seconds':300,'baseline_scope':'Retained 128 sources per pair, original three explicit exclusion snapshots, .25/.75; comparison of reference versus instrumented exact current loaders. Prior expected output identity is not fabricated across pack revisions.'};(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(sha(out/'manifest.json'))
if __name__=='__main__':main()
