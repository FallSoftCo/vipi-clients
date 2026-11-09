"""Join frozen independent-agent labels without adjudicating disagreements."""
import hashlib,json
from pathlib import Path
W=Path('/home/ai/Development/investigations/vipi-context-rule-lookup-20261109-r01')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 packet=json.loads((W/'apply/blind-review-packet.json').read_text());a=json.loads((W/'author-review-r01.json').read_text());b=json.loads((W/'root-review-r01.json').read_text());key=json.loads((W/'apply/review-method-key.json').read_text())
 assert a['packet_sha256']==b['packet_sha256']==sha(W/'apply/blind-review-packet.json')
 reviews={name:{c['case_id']:{o['option_id']:o for o in c['options']} for c in r['cases']} for name,r in [('author',a),('root',b)]};rows=[];dis=[]
 for c in packet['cases']:
  for o in c['options']:
   labels={name:m[c['case_id']][o['option_id']] for name,m in reviews.items()};row={'case_id':c['case_id'],'option_id':o['option_id'],'original_labels':labels,'zero_immersion':o['zero_immersion']};rows.append(row)
   if labels['author'].get('severity',labels['author'].get('label'))!=labels['root'].get('severity',labels['root'].get('label')):dis.append(row)
 counts={}
 for name,m in reviews.items():
  counts[name]={}
  for method in ['default','narrow','wide']:
   values=[m[k['case_id']][k['methods'][method]] for k in key];counts[name][method]={'cases':len(values),'strict_nonzero':sum(x.get('severity',x.get('label'))=='correct' and not x['zero_immersion'] for x in values),'minor_tolerant_nonzero':sum(x.get('severity',x.get('label')) in ['correct','minor_issue'] and not x['zero_immersion'] for x in values),'zero_immersion':sum(x['zero_immersion'] for x in values)}
 out={'packet_sha256':sha(W/'apply/blind-review-packet.json'),'review_hashes':{n:sha(W/(n+'-review-r01.json')) for n in ['author','root']},'raw_join':rows,'disagreements':dis,'method_counts':counts,'no_majority_gold':True,'independent_agents_not_human_validation':True,'stratified_reused_benchmark_not_population_accuracy':True};p=W/'joined-review-r01.json';assert not p.exists();p.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'sha256':sha(p),'options':len(rows),'disagreements':len(dis),'method_counts':counts}))
if __name__=='__main__':main()
