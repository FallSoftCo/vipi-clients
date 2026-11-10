#!/usr/bin/env python3
from pathlib import Path
import json,hashlib,collections
W=Path('/home/ai/Development/investigations/vipi-source-context-frames-20261109-r01')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 out=W/'joined-r01';assert not out.exists();out.mkdir()
 author=json.loads((W/'author-review-r01.json').read_text());root=json.loads((W/'root-review-r01.json').read_text());packet=json.loads((W/'review-merged-r01/anonymous-review.json').read_text());key=json.loads((W/'review-merged-r01/method-key.json').read_text())
 assert author['packet_sha256']==root['anonymous_sheet_sha256']==sha(W/'review-merged-r01/anonymous-review.json')
 aa={x['option_id']:x for x in author['judgments']};rr={x['option_id']:x for x in root['labels']};kk={x['option_id']:x['bindings'] for x in key};normalize={'compatible':'correct','minor':'minor_issue','empty':'empty','uncertain':'uncertain'};joined=[];disagreements=[];metrics={}
 for c in packet['cases']:
  for o in c['options']:
   oid=o['option_id'];a=aa[oid];r=rr[oid];rn=normalize[r['label']];item={'case_id':c['case_id'],'option_id':oid,'source':c['source'],'pair':c['pair'],'option':o,'author':a,'root':r,'normalized_root_label':rn,'disagreement':a['label']!=rn};joined.append(item)
   if item['disagreement']:disagreements.append(item)
   for b in kk[oid]:
    for who,label in [('author',a['label']),('root',rn)]:
     k=(who,b['platform'],b['pair'],b['state'],b['density'],b['layer'],b['arm']);m=metrics.setdefault(k,collections.Counter());m[label]+=1;m['rows']+=1;m['strict_nonempty']+=label=='correct';m['minor_tolerant_nonempty']+=label in ['correct','minor_issue']
 assert len(joined)==len(aa)==len(rr)==len(kk)==521
 result={'reviews_preserved':True,'majority_gold':False,'option_disagreements':len(disagreements),'joined':joined,'strata':[dict(zip(['reviewer','platform','pair','state','density','layer','arm'],k),**v) for k,v in sorted(metrics.items())]}
 for n,x in [('joined.json',result),('disagreements.json',disagreements)]: (out/n).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
 inputs=['author-review-r01.json','root-review-r01.json','review-merged-r01/anonymous-review.json','review-merged-r01/method-key.json'];(out/'receipt.json').write_text(json.dumps({'script_sha256':sha(Path(__file__)),'input_sha256':{n:sha(W/n) for n in inputs},'files':{n:sha(out/n) for n in ['joined.json','disagreements.json']}},indent=2)+'\n');print(json.dumps({'options':len(joined),'disagreements':len(disagreements),'author':author['counts'],'root':root['counts']}))
if __name__=='__main__':main()
