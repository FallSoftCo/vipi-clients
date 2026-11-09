import collections,hashlib,json,os,resource,signal,time
from pathlib import Path
R=Path('/srv/fallsoft/staging/vipi-apertium-lexical-selection-20261109-r01');N=Path('/srv/fallsoft/staging/vipi-contextual-lexical-selection-20261109-r01');A=Path('/srv/fallsoft/staging/vipi-apertium-occurrence-roles-20261109-r01')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def main():
 start=time.monotonic();os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});os.nice(10);resource.setrlimit(resource.RLIMIT_AS,(1024**3,)*2);signal.alarm(120);out=R/'post-audit-r01';out.mkdir(exist_ok=False);receipt=json.loads((R/'cohort/receipt.json').read_text());assert receipt['complete']
 for n in ('predictions.json','endpoint-mapping.json'):assert sha(R/'cohort'/n)==receipt['outputs'][n]['sha256']
 pred=json.loads((R/'cohort/predictions.json').read_text());maps=json.loads((R/'cohort/endpoint-mapping.json').read_text());data=json.loads((N/'prepare/dataset.json').read_text());morph=json.loads((R/'morphology-audit-r02/all-emitted-form-audit.json').read_text());byid={x['id']:x for x in data['rows']};nb={x['id']:x for x in json.loads((N/'compare/predictions.json').read_text())};unqualified=[x for x in morph if x['method']=='bilingual_default' and not x['qualified_exact_tags']];qualified={x['id'] for x in morph if x['method']=='bilingual_default' and x['qualified_exact_tags']};mapping=collections.Counter();rawcounts=collections.Counter();changes=[];traces=[];focus_changes=[]
 for k,m in maps.items():
  assert len(m['before'])==len(m['after'])
  for i,(a,b) in enumerate(zip(m['before'],m['after'])):
   rawcounts['all_units']+=1
   if a!=b:
    rawcounts['changed_alternative_lists']+=1;changes.append({'endpoint':k,'unit_index':i,'before':a,'after':b,'source':data['endpoints'][k],'normal_source_analysis':m['source_analyses'][i] if m['mapped'] else None})
   if a[:1]!=b[:1]:rawcounts['changed_first_any_unit']+=1
  p=Path(m['stage_root'])/'lexical.stderr'
  if p.exists():traces.append({'endpoint':k,'path':str(p),'sha256':sha(p),'lines':p.read_text().splitlines(),'source':data['endpoints'][k]})
 for x in pred:
  if not x['mapped']:
   failed=[k for k,v in x['sequence_identity'].items() if not v];mapping['unavailable']+=1;mapping['first_failure_'+(failed[0] if failed else 'focus_span')]+=1
   for f in failed:mapping['overlapping_'+f]+=1
  else:
   m=maps[x['endpoint']];i=m['source_spans'].index(x['source_span'])
   if m['before'][i]!=m['after'][i]:focus_changes.append({'id':x['id'],'development16':x['development16'],'source':data['endpoints'][x['endpoint']],'before':m['before'][i],'after':m['after'][i]})
 comparable=[x for x in pred if x['id'] in qualified and nb[x['id']]['methods']['default']['target'] is not None];summary={'source_mapping_losses':dict(mapping),'raw_stream_counts':dict(rawcounts),'trace_files':len(traces),'trace_lines':sum(len(x['lines']) for x in traces),'focus_alternative_list_changes':len(focus_changes),'focus_alternative_changes_development16':sum(x['development16'] for x in focus_changes),'first_choice_changes_all781':sum(x['lrx_changes_first_analysis'] for x in pred),'first_choice_changes_development16':sum(x['lrx_changes_first_analysis'] for x in pred if x['development16']),'qualified_exact_tag_outputs':len(qualified),'qualified_reference_agreement':sum(x['methods']['bilingual_default']['agrees_reference'] for x in pred if x['id'] in qualified),'qualified_zero_immersion':sum(x['methods']['bilingual_default']['zero_immersion'] for x in pred if x['id'] in qualified),'unqualified_output_count':len(unqualified),'unqualified_flag_counts':dict(collections.Counter(f for x in unqualified for f in x['flags'])),'nb_default_comparison_same_qualified_cases':{'denominator':len(comparable),'bilingual_and_lrx_reference_agreement':sum(x['methods']['bilingual_default']['agrees_reference'] for x in comparable),'nb_default_reference_agreement':sum(nb[x['id']]['methods']['default']['agrees_with_any_observed_face'] for x in comparable),'different_faces':sum(x['methods']['bilingual_default']['target']!=nb[x['id']]['methods']['default']['target'] for x in comparable)},'shipped_autolex':{'path':str(A/'root/usr/share/apertium/apertium-eng-spa/eng-spa.autolex.bin'),'bytes':(A/'root/usr/share/apertium/apertium-eng-spa/eng-spa.autolex.bin').stat().st_size,'sha256':sha(A/'root/usr/share/apertium/apertium-eng-spa/eng-spa.autolex.bin')},'no_new_inference':True}
 for name,value in {'summary.json':summary,'rule-firings-and-alternatives.json':{'all_changed_units':changes,'all_traces':traces,'all_focus_alternative_changes':focus_changes},'unqualified-outputs.json':unqualified}.items():
  raw=(json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode();assert len(raw)<2*1024**2;(out/name).write_bytes(raw)
 result={'complete':True,'seconds':time.monotonic()-start,'VmHWM_bytes':int(next(s.split()[1] for s in Path('/proc/self/status').read_text().splitlines() if s.startswith('VmHWM:')))*1024,'code_sha256':sha(Path(__file__)),'outputs':{p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in out.iterdir() if p.is_file()}};(out/'receipt.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));print(json.dumps(summary))
if __name__=='__main__':main()
