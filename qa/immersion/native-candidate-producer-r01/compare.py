import pathlib,json,sys,statistics,hashlib
p=pathlib.Path(__file__).parent;ref=json.loads(pathlib.Path('/home/ai/Development/investigations/vipi-native-candidate-producer-20261109-r01/reference.json').read_text());out=json.loads(pathlib.Path(sys.argv[1]).read_text());diff=[]
def compare(a,b,path):
 if type(a)!=type(b):
  if isinstance(a,(float,int)) and isinstance(b,(float,int)) and a==b:return
  diff.append({'path':path,'expected':a,'actual':b});return
 if isinstance(a,dict):
  for k in sorted(set(a)|set(b)):
   if k not in a or k not in b:diff.append({'path':path+'/'+k,'expected':a.get(k),'actual':b.get(k)})
   else:compare(a[k],b[k],path+'/'+k)
 elif isinstance(a,list):
  if len(a)!=len(b):diff.append({'path':path+'/length','expected':len(a),'actual':len(b)})
  for i,(x,y) in enumerate(zip(a,b)):compare(x,y,path+'/'+str(i))
 elif a!=b:diff.append({'path':path,'expected':a,'actual':b})
for r,o in zip(ref['cases'],out['cases']):
 d=o['diagnostic'];base=r['case_id']
 for k in ['candidates','baseline_candidate_count','geometry_rejections','experimental_geometry_rejections']:compare(r[k],d[k],base+'/'+k)
 for key,v in r['original_gates'].items():
  got=d['gates'].get(key,{})
  for k in ['candidate_indices','admitted_indices','chosen_rule_id','chosen_context_utf16','reason']:compare(v[k],got.get(k),base+'/gate/'+key+'/'+k)
 compare(sorted(r['original_gates']),sorted(d['gates']),base+'/gate_keys')
 for state in ['all_function','all_function_global300']:
  for arm in ['baseline','experimental']:compare(r['original_decisions'][state][arm],d['selections'][state][arm],base+'/'+state+'/'+arm)
  compare(r['original_qualified_decisions'][state],d['selections'][state]['qualified'],base+'/'+state+'/qualified')
times=[r['diagnostic']['elapsed_ns']/1e6 for r in out['cases']];result={'cases':len(out['cases']),'candidate_occurrences':sum(len(x['diagnostic']['candidates']) for x in out['cases']),'differences':diff,'equal':not diff,'identity_preparation_ms':out['identity_preparation_ns']/1e6,'producer_ms':{'min':min(times),'median':statistics.median(times),'max':max(times)},'input_sha256':hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest()};path=pathlib.Path(sys.argv[1]).with_suffix('.comparison.json');path.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='differences'}));print(json.dumps(diff[:12],indent=2))
