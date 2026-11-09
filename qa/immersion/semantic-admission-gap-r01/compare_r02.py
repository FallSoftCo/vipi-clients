"""Read-only evidence-gate ablation; approval required, no asset mutation."""
import collections,gzip,hashlib,importlib.util,json,os,pathlib,resource,shutil,signal,socket,sqlite3,time,zlib
R=pathlib.Path('/srv/fallsoft/staging/vipi-semantic-admission-gap-20261109-r01')
STATES=['all_function','all_function_global300']
def enc(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def sha(p):
 with open(p,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def permit(meta,role):
 if not meta['baseline']:return True,'qualified_addon_unchanged'
 forms=[x for x in meta['eligible_source_forms'] if x['pos']==role]
 if not forms:return False,'no_actual_role_link'
 if any(x['source_safe'] for x in forms):return True,'eligible_source_safe'
 if meta['context_tokens']<=meta['focus_tokens']:return False,'unsafe_without_wider_context'
 if meta['components']<2:return False,'unsafe_context_single_component'
 return True,'unsafe_repeated_wider_context'
def controls():
 m={'baseline':True,'eligible_source_forms':[{'pos':'adv','source_safe':False},{'pos':'noun','source_safe':True}],'context_tokens':1,'focus_tokens':1,'components':106}
 assert permit(m,'adv')==(False,'unsafe_without_wider_context')
 assert permit(m,'noun')[0]
 m['context_tokens']=2;m['components']=1;assert not permit(m,'adv')[0]
 m['components']=2;assert permit(m,'adv')[0]
 assert not permit(m,None)[0]
 m['baseline']=False;assert permit(m,None)[0]
 return {'role_specific_safe_link':True,'safe_unigram_preserved':True,'unsafe_unigram_high_support_withheld':True,'unsafe_multiword_one_component_withheld':True,'unsafe_multiword_two_components_retained':True,'qualified_addon_unchanged':True}
def allowed(t,gates):
 return [i for i,c in enumerate(t['candidates'][:t['baseline_candidate_count']]) if not c['filter_reasons']]+sorted({i for g in gates.values() for i in g['admitted_indices']})
def main(p,out,write):
 paths={k:v['path'] for k,v in p['inputs'].items()}
 for k,v in p['inputs'].items():assert sha(v['path'])==v['sha256'],k
 common=load('frozen_common',paths['common']);selector=load('frozen_selector',paths['selector'])
 order=json.load(open(paths['family_control']))['learned_family_order']
 # Exercise actual selector: removing unsafe candidate never removes its enclosing source-unit mask.
 def c(i,span):return dict(id=str(i),concept_id=str(i),focus_utf16=span,context_utf16=span,source='x',target='y',reading=[],identical_face=False,category='content',knowledge_ids=['x'],train_rank=i,cost=1,context_native_cost=1)
 t={'id':'mechanism','text':'aa bb cc','native_words_utf16':[[0,2],[3,5],[6,8]],'protected_ranges_utf16':[],'source_masks':[{'unit_id':'mask','utf16':[0,5]}],'candidates':[c(0,[3,5]),c(1,[6,8])]}
 s=common.translated(selector,t,[0,1],'all_function',[]);assert s['selected_indices']==[1];assert 'inside_recognized_source_unit' in s['rejected'][0]['reasons'];assert t['source_masks']==[{'unit_id':'mask','utf16':[0,5]}]
 write('controls.json',dict(controls(),functional_mask_preserved=True))
 cat=sqlite3.connect('file:'+paths['catalog']+'?mode=ro',uri=True);heads=sqlite3.connect('file:'+paths['heads']+'?mode=ro',uri=True)
 meta={}
 for ident,baseline,raw in cat.execute('SELECT id,baseline,record_json FROM candidates ORDER BY id'):
  rec=json.loads(raw)
  if not baseline:meta[ident]={'baseline':False};continue
  forms={}
  for blob, in cat.execute("SELECT e.value_json FROM head_evidence h JOIN evidence e ON e.id=h.evidence_id WHERE h.head_id=? AND h.kind='source_form'",(ident,)):
   f=json.loads(blob);forms[f['form_id']]=f
  links=[x for x in rec['head_shared_senses'] if x['structural_eligible']]
  assert links and all(not x['reasons'] for x in links)
  fids=sorted({x['source_form_id'] for x in links});assert all(x in forms for x in fids)
  blob=heads.execute('SELECT proof FROM contexts WHERE id=?',(rec['context_id'],)).fetchone()[0];proof=json.loads(zlib.decompress(blob));a,b=rec['source_focus_relative_tokens']
  meta[ident]={'baseline':True,'context_id':rec['context_id'],'source_key':rec['source_key'],'context_tokens':len(rec['source_context_token_text']),'focus_tokens':b-a,'components':proof['variant']['distinct_components'],'proof_blob_sha256':hashlib.sha256(blob).hexdigest(),'record_sha256':hashlib.sha256(raw.encode()).hexdigest(),'eligible_source_forms':[forms[x] for x in fids],'eligible_links':links}
 write('head-gate-evidence.json',meta)
 current={x['id']:x for x in map(json.loads,gzip.open(paths['qualified'],'rt'))};assert len(current)==9535
 refs={x['case_id']:x for x in json.load(open(paths['reference']))['cases']}
 native=json.load(open(paths['native']))['cases'];assert len(native)==52
 def streams():
  with gzip.open(paths['trace'],'rt') as f:
   for line in f:
    t=json.loads(line);q=current[t['id']];yield 'train',t,allowed(t,q['gates']),q['qualified']
  for row in native:
   a=row['actual'];ref=refs[row['case_id']];t=dict(a,id=row['case_id'],text=ref['original']);yield 'native52',t,allowed(t,a['gates']),{k:a['selections'][k]['qualified'] for k in STATES}
 # Whole baseline parity is a prerequisite; no candidate-gated selections in this pass.
 parity=collections.Counter()
 for cohort,t,indices,prior in streams():
  assert len(indices)==len(set(indices)) and indices==sorted(indices)
  for known in STATES:
   result=common.translated(selector,t,indices,known,order);assert result==prior[known],(cohort,t['id'],known,'full_current_parity');parity[cohort]+=1
 write('parity.json',{'complete':True,'full_decisions':dict(parity),'new_gate_not_yet_selected':True})
 metrics=collections.defaultdict(collections.Counter);reasons=collections.Counter();rawbytes=0;actual=[]
 with gzip.open(out/'deltas.jsonl.gz','xb',compresslevel=6) as f:
  for cohort,t,indices,prior in streams():
   cs=t['candidates'];admission={i:permit(meta[cs[i]['head_id']],cs[i]['role']['mapped']) for i in indices};keep=[i for i in indices if admission[i][0]];reasons.update(cohort+'|'+r for ok,r in admission.values());arms={}
   for known in STATES:
    before=prior[known];after=common.translated(selector,t,keep,known,order);m=metrics[cohort+'|'+known];m['messages']+=1;m['native_words']+=len(t['native_words_utf16']);m['before_nonempty']+=bool(before['selected_indices']);m['after_nonempty']+=bool(after['selected_indices']);m['before_words']+=sum(cs[i]['cost'] for i in before['selected_indices']);m['after_words']+=sum(cs[i]['cost'] for i in after['selected_indices']);bs=set(before['selected_indices']);ss=set(after['selected_indices']);m['lost_emissions']+=len(bs-ss);m['new_emissions']+=len(ss-bs);m['empty_losses']+=bool(bs) and not ss;m['empty_gains']+=not bs and bool(ss);m['changed_messages']+=before['mixed_output']!=after['mixed_output'];arms[known]={'before':before,'after':after,'lost_indices':sorted(bs-ss),'added_indices':sorted(ss-bs)}
   v={'cohort':cohort,'id':t['id'],'withheld':[{'index':i,'reason':admission[i][1]} for i in indices if not admission[i][0]],'states':arms}
   if cohort=='native52':actual.append(dict(v,text=t['text'],candidates=cs))
   if v['withheld'] or cohort=='native52':
    raw=(enc(v)+'\n').encode();rawbytes+=len(raw);assert rawbytes<=24*1024**2,'uncompressed compact delta quota';f.write(raw)
 write('native52.json',actual);write('metrics.json',{'counts':{k:dict(v) for k,v in metrics.items()},'candidate_admission_reasons':dict(reasons),'raw_delta_bytes':rawbytes,'accuracy_claim':False,'source_context_support_not_meaning_certificate':True})
if __name__=='__main__':
 if len(__import__('sys').argv)>1 and __import__('sys').argv[1]=='--controls':print(enc(controls()));raise SystemExit
 assert socket.gethostname()=='fallsoft-production-20261106'
 start=time.monotonic();p=json.loads((R/'protocol.json').read_text());approval=json.loads((R/'root-run-approval.json').read_text());assert approval['run'] is True and approval['protocol_sha256']==sha(R/'protocol.json') and approval['code_sha256']==sha(__file__)
 os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});os.nice(10);resource.setrlimit(resource.RLIMIT_AS,(1024**3,)*2);signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('120 seconds')));signal.alarm(120)
 assert shutil.disk_usage(R).free>8*1024**3+32*1024**2;out=R/'outputs';out.mkdir(exist_ok=False);receipt={'complete':False,'protocol_sha256':sha(R/'protocol.json'),'code_sha256':sha(__file__)}
 def write(name,value):
  b=(enc(value)+'\n').encode();assert len(b)+sum(x.stat().st_size for x in out.iterdir() if x.is_file())<=32*1024**2;(out/name).write_bytes(b)
 try:main(p,out,write);receipt['complete']=True
 except BaseException as e:receipt['error']=repr(e);raise
 finally:
  receipt.update(seconds=time.monotonic()-start,VmHWM_bytes=int(next(x.split()[1] for x in pathlib.Path('/proc/self/status').read_text().splitlines() if x.startswith('VmHWM:')))*1024,outputs={x.name:{'bytes':x.stat().st_size,'sha256':sha(x)} for x in out.iterdir() if x.is_file()});(out/'receipt.json').write_text(enc(receipt)+'\n');print(enc(receipt),flush=True)
