#!/usr/bin/env python3
import argparse,hashlib,json
from pathlib import Path

def main():
 p=argparse.ArgumentParser();p.add_argument('--capture',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--independent',type=Path,required=True);a=p.parse_args();j=json.loads(a.capture.read_text());out=[]
 for r in j['rows']:
  for lang,t in r['targets'].items():
   scopes={}
   for arm,v in t['arms'].items():
    for s in v['spans']:
     key=(r['id'],lang,s['start'],s['end'],s['translated']);sid=hashlib.sha256(json.dumps(key,ensure_ascii=False).encode()).hexdigest()[:16]
     if sid not in scopes:scopes[sid]=dict(s,scope_id=sid,arms=[])
     scopes[sid]['arms'].append(arm)
   out.append({'id':r['id']+'-en-'+lang,'source_case_id':r['id'],'source':r['text'],'target_language':lang,'source_words':t['source_words'],'sampling_length_bin':r['sampling_length_bin'],'train_surface_overlap':r['train_surface_overlap'],'previously_evaluated_or_seen_surface_overlap':r['previously_evaluated_or_seen_surface_overlap'],'review_only_preceding_context':r['review_only_preceding_context'],'independent24':r.get('independent24',False),'scopes':list(scopes.values()),'default25_mixed_outputs':{arm:v['mixed_text'] for arm,v in t['arms'].items() if '|0.25|' in arm}})
 base={'production':False,'labels_included':False,'kind':j['kind'],'capture_sha256':hashlib.sha256(a.capture.read_bytes()).hexdigest(),'policy_freeze_sha256':j['policy_freeze_sha256'],'scope_policy':'Exact source scopes deduplicated across three policies, three densities and four learned-concept states. Scope arms explicitly retained; current native runtime and translation providers absent.','review_type':'Context-disjoint source-only projection. Target inventory/prior diagnostic reviewed before this sample; no claim of reviewer unfamiliarity with targets or repeated surfaces.'}
 for path,rows in [(a.output,out),(a.independent,[r for r in out if r['independent24']])]:
  assert not path.exists();path.write_text(json.dumps(dict(base,rows=rows),ensure_ascii=False,indent=2)+'\n');print(path.name,len(rows),sum(len(r['scopes']) for r in rows),hashlib.sha256(path.read_bytes()).hexdigest())
if __name__=='__main__':main()
