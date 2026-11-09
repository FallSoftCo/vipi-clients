"""Join frozen independent reviews without harmonizing their labels."""
import collections,hashlib,json
from pathlib import Path
W=Path('/home/ai/Development/investigations/vipi-contextual-lexical-selection-20261109-r01')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 out=W/'joined-r01';out.mkdir(exist_ok=False);expected={'author-review-r01.json':'6f9e595fd06d06b6d548cc8c4384d40e7d2891f4dcfb1beaf5a32991bae11935','root-review-r01.json':'97d371c743825c0cde8523cd98a7548e9bf4559f6b74422461c20a2b66c3037a','compare/blind-review-packet.json':'2c8352a1582c1e570a978e1befddc6fb37986e7fb31a623bcbc122ba8d573f8c'}
 for name,h in expected.items():assert sha(W/name)==h
 bundle=json.loads((W/'metadata-bundle.json').read_text());packet=json.loads((W/'compare/blind-review-packet.json').read_text());key=bundle['compare/review-method-key.json']['data'];assert bundle['compare/receipt.json']['data']['complete'];assert bundle['identity-preflight.json']['data']['prediction_allowed'];expected['metadata-bundle.json']=sha(W/'metadata-bundle.json')
 for name in ('metrics.json','review-method-key.json','review-selection-freeze.json','training-support.json'):
  assert bundle['compare/'+name]['sha256']==bundle['compare/receipt.json']['data']['outputs'][name]['sha256']
 a=json.loads((W/'author-review-r01.json').read_text());b=json.loads((W/'root-review-r01.json').read_text());maps={'author':{(x['case_id'],x['option_id']):x for x in a['option_reviews']},'root':{(x['case_id'],x['option_id']):x for x in b['options']}};normalize={'minor':'minor_issue','material':'material_error'};rows=[];diff=[]
 for c in packet['cases']:
  for o in c['options']:
   idx=(c['case_id'],o['option_id']);values={who:m[idx] for who,m in maps.items()};assert all(v['target']==o['target'] for v in values.values());labels={who:normalize.get(v['label'],v['label']) for who,v in values.items()};row={'case_id':idx[0],'option_id':idx[1],'target':o['target'],'raw_reviews':values,'normalized_labels':labels};rows.append(row)
   if len(set(labels.values()))>1:diff.append(row)
 assert len(rows)==len(maps['author'])==len(maps['root'])==24
 aggregate={};paired={}
 for who,m in maps.items():
  aggregate[who]={};paired[who]={}
  for stratum in ('all','changed','same_ambiguous','single_target'):
   ks=[k for k in key if stratum=='all' or k['stratum']==stratum];aggregate[who][stratum]={};paired[who][stratum]={}
   for method in ('default','local','sentence'):
    labels=[normalize.get((v:=m[(k['case_id'],k['method_options'][method])])['label'],v['label']) for k in ks];aggregate[who][stratum][method]={'cases':len(ks),'labels':dict(collections.Counter(labels)),'strict_acceptable':labels.count('correct'),'minor_tolerant_acceptable':sum(x in ('correct','minor_issue') for x in labels),'zero_immersion':sum(m[(k['case_id'],k['method_options'][method])]['zero_immersion'] for k in ks)}
    transitions=collections.Counter();strictgain=strictloss=materialgain=materialloss=0
    for k in ks:
     base=m[(k['case_id'],k['method_options']['default'])]['label'];v=m[(k['case_id'],k['method_options'][method])]['label'];base=normalize.get(base,base);v=normalize.get(v,v);transitions[base+' -> '+v]+=1;strictgain+=base!='correct' and v=='correct';strictloss+=base=='correct' and v!='correct';materialgain+=base=='material_error' and v in ('correct','minor_issue');materialloss+=base in ('correct','minor_issue') and v=='material_error'
    paired[who][stratum][method]={'transitions':dict(transitions),'strict_gains':strictgain,'strict_losses':strictloss,'material_removed_to_acceptable':materialgain,'material_introduced_from_acceptable':materialloss}
 joined={'input_hashes':expected,'method_key':key,'all_option_reviews':rows,'disagreements':diff,'stratified_per_reviewer':aggregate,'paired_per_reviewer':paired,'no_majority_gold':True,'population_accuracy_claim':False,'notes':'Only label spelling minor/material normalized; original judgments/reasons/references retained verbatim. Uncertain never counted accepted. Methods decoded only after both independent reviews froze.'};(out/'joined.json').write_text(json.dumps(joined,ensure_ascii=False,indent=2)+'\n');summary={'disagreements':[{k:x[k] for k in ('case_id','option_id','target','normalized_labels')} for x in diff],'stratified_per_reviewer':aggregate,'paired_per_reviewer':paired,'split_counts':bundle['split-counts'],'training':{pool:{'keys':len(v:=[x for x in bundle['compare/training-support.json']['data'] if x['pool']==pool]),'keys_with_multiple_targets':sum(len(x['targets'])>1 for x in v),'conflict_occurrences':sum(x['conflict_occurrences'] for x in v),'keys_with_lt3_components':sum(x['components']<3 for x in v)} for pool in ('explicit','direct')}};(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');(out/'receipt.json').write_text(json.dumps({'complete':True,'code_sha256':sha(Path(__file__)),'inputs':expected,'outputs':{p.name:sha(p) for p in out.iterdir() if p.is_file()}},indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
