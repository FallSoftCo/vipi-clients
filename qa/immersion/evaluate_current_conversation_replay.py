#!/usr/bin/env python3
"""Validate identity-preserving native replay and report aggregate availability."""
import argparse,hashlib,json,math,statistics
from pathlib import Path

def sha(p):return hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--report',type=Path,required=True);p.add_argument('--catalog',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 manifest=json.loads((a.input/'manifest.json').read_text());report=json.loads(a.report.read_text())
 assert report['schema']=='vipi-current-conversation-replay-1' and report['input_manifest_sha256']==sha(a.input/'manifest.json')
 assert report['catalog_sha256']==sha(a.catalog) and report['translation_reused'] and not report['classification_exercised']
 assert report['independent_semantic_acceptance'] is False and report['release_ready'] is False
 summaries=[];total=0
 for entry,result in zip(manifest['files'],report['datasets'],strict=True):
  path=a.input/entry['file'];assert sha(path)==entry['sha256'];source=json.loads(path.read_text())
  assert source['name']==result['name'] and source['capture_sha256']==result['capture_sha256'] and source['corpus_sha256']==result['corpus_sha256']
  by_source={};elapsed=[];cases=spans=with_immersion=protected=exact=invalid=0
  for original,pair in zip(source['pairs'],result['pairs'],strict=True):
   assert (original['source'],original['target'])==(pair['source'],pair['target'])
   assert [r['id'] for r in original['samples']]==[r['id'] for r in pair['outcomes']]
   assert pair['cases']==len(pair['outcomes'])
   assert pair['selected_spans']==sum(r['selected'] for r in pair['outcomes'])
   assert pair['with_immersion']==sum(r['selected']>0 for r in pair['outcomes'])
   assert all(r['selected']==0 or r['identifier_guard'] for r in pair['outcomes'])
   cases+=pair['cases'];spans+=pair['selected_spans'];with_immersion+=pair['with_immersion'];protected+=pair['identifier_abstentions'];exact+=pair['exact_references'];invalid+=pair['invalid_inputs']
   elapsed.extend(r['elapsed_ms'] for r in pair['outcomes'])
   item=by_source.setdefault(pair['source'],{'cases':0,'with_immersion':0,'selected_spans':0})
   for key in item:item[key]+=pair[key]
  assert cases==entry['cases'];total+=cases
  ordered=sorted(elapsed)
  summaries.append({'name':source['name'],'cases':cases,'with_immersion':with_immersion,'availability_fraction':with_immersion/cases,'selected_spans':spans,'identifier_abstentions':protected,'invalid_inputs':invalid,'exact_references':exact,'by_source':by_source,'median_ms':statistics.median(elapsed),'p95_ms':ordered[math.ceil(len(ordered)*.95)-1]})
 assert total==report['cases']==9900 and set(report['source_languages'])=={'en','zh','ar','fr','it','ja','ko'}
 output={'schema':'vipi-current-conversation-replay-summary-1','report_sha256':sha(a.report),'catalog_sha256':sha(a.catalog),'input_manifest_sha256':sha(a.input/'manifest.json'),'cases':total,'source_languages':report['source_languages'],'datasets':summaries,'limits':['Past native translations are reused; neither translator nor language classifier rerun.','Maximum-density mapping availability after production identifier checks, not substitution accuracy.','Reused diagnostic corpora; no untouched acceptance, general-chat fluency or release claim.'],'independent_semantic_acceptance':False,'release_ready':False}
 with a.output.open('x') as f:json.dump(output,f,indent=2);f.write('\n')
 print(json.dumps(output,ensure_ascii=False))
if __name__=='__main__':main()
