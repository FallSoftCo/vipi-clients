"""Additive reporting only: keep original predictions/metric definitions immutable."""
import collections,hashlib,json
from pathlib import Path
W=Path('/home/ai/Development/investigations/vipi-context-rule-lookup-20261109-r01')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 rows=json.loads((W/'apply/predictions.json').read_text());out={}
 for name,subset in [('all',rows),('multi_target',[x for x in rows if len(x['train_faces'])>1])]:
  out[name]={}
  for method in ['default','narrow','wide']:
   hist=collections.Counter();unavailable=same=0
   for x in subset:
    v=x['methods'][method];unavailable+=v['target'] is None;same+=v['target'] is not None and v['zero_immersion']
    if method!='default' and v['chosen_rule_id']:
     a,b=v['chosen_context_tokens'];hist[str((b-a,x['source_focus_index']-a))]+=1
   out[name][method]={'records':len(subset),'unavailable':unavailable,'emitted_same_source_face':same,'emitted_changed_source_face':len(subset)-unavailable-same,'winning_rule_length_focus_offset':dict(hist)}
  changes=[]
  for x in subset:
   wide=x['methods']['wide'];narrow=x['methods']['narrow']
   if wide['target']==narrow['target']:continue
   a,b=wide['chosen_context_tokens'];changes.append({'id':x['id'],'length':b-a,'focus_offset':x['source_focus_index']-a,'narrow_target':narrow['target'],'wide_target':wide['target'],'reference_gain':wide['reference_agreement'] and not narrow['reference_agreement'],'reference_loss':narrow['reference_agreement'] and not wide['reference_agreement']})
  out[name]['wide_vs_narrow_changes']=changes
 p=W/'prediction-reporting-audit-r01.json';assert not p.exists();p.write_text(json.dumps({'predictions_sha256':sha(W/'apply/predictions.json'),'code_sha256':sha(Path(__file__)),'counts':out,'no_prediction_change':True},ensure_ascii=False,indent=2)+'\n');print(p)
if __name__=='__main__':main()
