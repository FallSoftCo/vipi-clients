"""Existing EN->ES bilingual/LRX comparison; no grammar output or activation."""
import collections,functools,hashlib,importlib.util,json,os,re,resource,shutil,signal,socket,sqlite3,subprocess,sys,time,unicodedata
from pathlib import Path
R=Path('/srv/fallsoft/staging/vipi-apertium-lexical-selection-20261109-r01');A=Path('/srv/fallsoft/staging/vipi-apertium-occurrence-roles-20261109-r01');C=Path('/srv/fallsoft/staging/vipi-apertium-corpus-evidence-20261109-r01');N=Path('/srv/fallsoft/staging/vipi-contextual-lexical-selection-20261109-r01');MiB=1024**2

def enc(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(MiB),b''):h.update(b)
 return h.hexdigest()
def digest(x):return hashlib.sha256(enc(x).encode()).hexdigest()
def norm(t):return ' '.join(unicodedata.normalize('NFC',t).casefold().split())
def split(s,sep='/'):
 out=[];a=0;escape=False
 for i,c in enumerate(s):
  if escape:escape=False;continue
  if c=='\\':escape=True;continue
  if c==sep:out.append(s[a:i]);a=i+1
 out.append(s[a:]);return out

def units(s):
 result=[];a=None;esc=False;bracket=0
 for i,c in enumerate(s):
  if esc:esc=False;continue
  if c=='\\':esc=True;continue
  if a is None:
   if c=='[':bracket+=1
   elif c==']':bracket=max(0,bracket-1)
   elif c=='^' and not bracket:a=i
  elif c=='$':result.append({'begin':a,'end':i+1,'fields':split(s[a+1:i])});a=None
 assert a is None;return result

def strip_surface(s):
 result=[];cursor=0
 for u in units(s):
  assert len(u['fields'])==2,'one chosen analysis required';result.extend([s[cursor:u['begin']],'^'+u['fields'][1]+'$']);cursor=u['end']
 result.append(s[cursor:]);return ''.join(result)

def source_spans(s,text):
 cursor=0;lost=False;result=[]
 for u in units(s):
  assert len(u['fields'])==2;surface=re.sub(r'\\(.)',r'\1',u['fields'][0]);start=text.find(surface,cursor)
  if lost or start<0 or text[cursor:start].strip():
   result.append(None)
   if text[cursor:].strip():lost=True
  else:
   end=start+len(surface);result.append([len(text[:a].encode('utf-16-le'))//2 for a in (start,end)]);cursor=end
 return result

def signatures(analysis):
 if analysis.startswith(('*','@','#')) or len(split(analysis,'+'))!=1:return None
 tags=re.findall(r'<([^>]+)>',analysis);number=[x for x in tags if x in ('sg','pl','sp')]
 if not tags or tags[0]!='n' or len(number)!=1:return None
 lemma=norm(re.sub(r'<[^>]+>','',analysis));return [lemma,'n',number[0]]

def controls():
 s='^dog/dog<n><sg>$ ^dog/dog<n><sg>$';assert source_spans(s,'dog dog')==[[0,3],[4,7]];assert strip_surface(s)=='^dog<n><sg>$ ^dog<n><sg>$';assert source_spans('^New York/New York<np>$','New York')==[[0,8]];assert [0,3] not in source_spans('^New York/New York<np>$','New York');assert signatures('pedido<vblex><pp><m><sg>') is None;assert signatures('perro<n><m><pl>')==['perro','n','pl'];assert units('[x^fake$]^dog<n><sg>$')[0]['fields']==['dog<n><sg>'];return True

class Run:
 def __init__(self,stage):
  assert socket.gethostname()=='fallsoft-production-20261106';self.start=time.monotonic();self.last=self.start;self.p=json.loads((R/'protocol.json').read_text());assert sha(__file__)==self.p['code_sha256'];self.out=R/stage;self.out.mkdir(exist_ok=False);self.stage=stage;self.receipt={'complete':False,'stage':stage,'protocol_sha256':sha(R/'protocol.json')};os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});os.nice(10);resource.setrlimit(resource.RLIMIT_AS,(1024**3,)*2);signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('300s ceiling')));signal.alarm(300);assert shutil.disk_usage(R).free>8*1024**3+128*MiB;self.env=dict(os.environ,LD_LIBRARY_PATH=str(A/'root/usr/lib/x86_64-linux-gnu'),LC_ALL='C.UTF-8');self.child_seconds=0;self.child_count=0
 def verify(self):
  for k,v in self.p['inputs'].items():assert sha(v['path'])==v['sha256'],k
  old=json.loads((A/'protocol.json').read_text())
  for k,v in old['execution_assets'].items():assert sha(A/k)==v,k
 def save(self,name,data):
  if not isinstance(data,bytes):data=(json.dumps(data,ensure_ascii=False,indent=2)+'\n').encode()
  assert sum(p.stat().st_size for p in R.rglob('*') if p.is_file())+len(data)<64*MiB,'output quota; no truncation';p=self.out/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
 def child(self,cmd,value,label):
  start=time.monotonic();z=subprocess.run(cmd,input=value,capture_output=True,env=self.env,timeout=min(15,max(1,300-(time.monotonic()-self.start))));self.child_seconds+=time.monotonic()-start;self.child_count+=1;self.save(label+'.raw',z.stdout)
  if z.stderr:self.save(label+'.stderr',z.stderr)
  assert z.returncode==0,(label,z.returncode,z.stderr.decode());return z.stdout
 def finish(self,error=None):
  self.receipt.update(complete=error is None,error=error,seconds=time.monotonic()-self.start,child_seconds=self.child_seconds,child_processes=self.child_count,VmHWM_bytes=int(next(x.split()[1] for x in Path('/proc/self/status').read_text().splitlines() if x.startswith('VmHWM:')))*1024,outputs={str(p.relative_to(self.out)):{'bytes':p.stat().st_size,'sha256':sha(p)} for p in self.out.rglob('*') if p.is_file()});self.save('receipt.json',self.receipt);print(enc({k:v for k,v in self.receipt.items() if k!='outputs'}),flush=True)
 def progress(self,**counts):
  if time.monotonic()-self.last>45:print(enc(dict(stage=self.stage,seconds=time.monotonic()-self.start,**counts)),flush=True);self.last=time.monotonic()

class Pipeline:
 def __init__(self,r):
  self.r=r;self.db=sqlite3.connect((C/'annotation-r01/index.sqlite').as_uri()+'?mode=ro&immutable=1',uri=True);self.db.row_factory=sqlite3.Row;self.raw={k:(C/'annotation-r01'/(k+'.raw')).open('rb') for k in ('tag','morph')};self.bin=A/'root/usr/bin';self.data=A/'root/usr/share/apertium/apertium-eng-spa'
 def get(self,key,kind):
  row=self.db.execute('SELECT * FROM endpoints WHERE key=?',(key,)).fetchone();assert row;self.raw[kind].seek(row[kind+'_offset']);b=self.raw[kind].read(row[kind+'_bytes']);assert hashlib.sha256(b).hexdigest()==row[kind+'_sha'];return b
 def execute(self,key,e,qualification=False):
  tag=self.get(key,'tag');assert b'\0' not in tag;normal=strip_surface(tag.decode()).encode();self.r.save('stages/'+key+'/normal.raw',normal)
  if qualification:
   morph=self.get(key,'morph');actual=self.r.child([str(self.bin/'apertium-tagger'),'-g','-z',str(self.data/'eng-spa.prob')],morph+b'\0','stages/'+key+'/normal-tagger-validation');parts=actual.split(b'\0');assert parts[0]==normal and all(p==b'' for p in parts[1:]),'normal vs surface-preserving chosen-stream parity'
  values={'normal':normal}
  commands=[('pretransfer',[str(self.bin/'apertium-pretransfer')]),('genitive',[str(self.bin/'apertium-transfer'),'-n',str(self.data/'apertium-eng-spa.eng-spa.genitive.t1x'),str(self.data/'eng-spa.genitive.bin')]),('biltrans',[str(self.bin/'lt-proc'),'-b',str(self.data/'eng-spa.autobil.bin')]),('lexical',[str(self.bin/'lrx-proc'),'-m','-t',str(self.data/'eng-spa.autolex.bin')])]
  val=normal
  for stage,cmd in commands:val=self.r.child(cmd,val,'stages/'+key+'/'+stage);values[stage]=val
  lists={stage:units(raw.decode()) for stage,raw in values.items()};source=[u['fields'][0] for u in lists['normal']];checks={stage:[u['fields'][0] for u in lists[stage]]==source for stage in ('pretransfer','genitive','biltrans','lexical')};spans=source_spans(tag.decode(),e['text']);assert len(spans)==len(source)
  return {'endpoint':key,'source_text_sha256':hashlib.sha256(e['text'].encode()).hexdigest(),'source_geometry_sha256':digest(e['tokens']),'source_spans':spans,'source_analyses':source,'sequence_identity':checks,'mapped':all(checks.values()),'before':[u['fields'][1:] for u in lists['biltrans']],'after':[u['fields'][1:] for u in lists['lexical']],'stage_root':str(self.r.out/'stages'/key)}

def load_data(r):
 d=json.loads((N/'prepare/dataset.json').read_text());xs=[x for x in d['rows'] if x['pool']=='explicit' and x['split']=='test'];assert len(xs)==781;packet=json.loads((N/'compare/blind-review-packet.json').read_text());ids={c['stable_source_focus_id'] for c in packet['cases']};assert len(ids)==16;return d,xs,ids

def qualify(r):
 r.verify();assert controls();d,xs,ids=load_data(r);pipeline=Pipeline(r);keys=sorted({x['endpoint'] for x in xs if x['id'] in ids});assert len(keys)==16;maps={}
 for k in keys:maps[k]=pipeline.execute(k,d['endpoints'][k],True)
 # Exact mapping is required for a credited focus; sequence-changing cases abstain, not failure.
 results=[]
 for x in xs:
  if x['id'] not in ids:continue
  m=maps[x['endpoint']];indices=[i for i,s in enumerate(m['source_spans']) if s==x['span']];results.append({'id':x['id'],'mapped':m['mapped'] and len(indices)==1,'sequence_identity':m['sequence_identity'],'focus_matches':len(indices)})
 r.save('endpoint-mapping.json',maps);r.save('qualification.json',{'normal_tagger_byte_parity_all16':True,'mechanism_controls_passed':True,'source_focuses':results,'mapped':sum(x['mapped'] for x in results),'unavailable':sum(not x['mapped'] for x in results),'bounded_cohort_authorized_if_parity':True})

def cohort(r):
 r.verify();assert controls();qr=json.loads((R/'qualify/receipt.json').read_text());assert qr['complete'] and qr['protocol_sha256']==sha(R/'protocol.json')
 for name,h in qr['outputs'].items():assert sha(R/'qualify'/name)==h['sha256']
 q=json.loads((R/'qualify/qualification.json').read_text());assert q['normal_tagger_byte_parity_all16'] and q['mechanism_controls_passed'];maps=json.loads((R/'qualify/endpoint-mapping.json').read_text());d,xs,exposed=load_data(r);pipeline=Pipeline(r);allkeys=sorted({x['endpoint'] for x in xs})
 for i,k in enumerate(allkeys):
  if k not in maps:maps[k]=pipeline.execute(k,d['endpoints'][k])
  r.progress(endpoints=i+1,total=len(allkeys))
 db=sqlite3.connect((C/'join-r02/evidence.sqlite').as_uri()+'?mode=ro&immutable=1',uri=True);db.execute('PRAGMA query_only=ON')
 @functools.lru_cache(maxsize=10000)
 def obj(ref):
  z=db.execute('SELECT data FROM objects WHERE id=?',(ref,)).fetchone();assert z;return json.loads(z[0])
 pools={'train':collections.defaultdict(lambda:collections.defaultdict(lambda:collections.defaultdict(set))),'all_retained':collections.defaultdict(lambda:collections.defaultdict(lambda:collections.defaultdict(set)))}
 for x in d['rows']:
  if x['pool']!='explicit':continue
  for face,t in x['targets'].items():
   for rid in t['relation_refs']:
    relation=obj(rid);assert relation['original_form_number_term_eligible'] and relation['both_exact_form_roles_noun'] and not relation['original_envelope_reasons'] and not relation['exact_focus_reasons']
    tr=relation['target_role']
    for ref in tr['raw_analysis_refs']:
     unit=obj(ref)
     if unit['utf16']!=tr['actual_form_utf16'] or len(unit['contextual_readings'])!=1:continue
     sig=signatures(unit['contextual_readings'][0])
     if sig:
      key=enc(sig);pools['all_retained'][x['key']][key][face].add(rid)
      if x['split']=='train':pools['train'][x['key']][key][face].add(rid)
 rows=[]
 for x in xs:
  m=maps[x['endpoint']];indices=[i for i,s in enumerate(m['source_spans']) if s==x['span']];row={'id':x['id'],'key':x['key'],'component':x['component'],'endpoint':x['endpoint'],'source_span':x['span'],'development16':x['id'] in exposed,'sequence_identity':m['sequence_identity'],'mapped':m['mapped'] and len(indices)==1,'methods':{},'observed_faces':sorted(x['targets'])}
  for method,stage in [('bilingual_default','before'),('lexical_selection','after')]:
   out={'target':None,'reason':None,'analyses':[]}
   if not row['mapped']:out['reason']='untraceable_source_sequence_or_focus'
   else:
    index=indices[0];analyses=m[stage][index];out['analyses']=analyses;chosen=analyses[0] if analyses else None;out['chosen_analysis']=chosen;sig=signatures(chosen) if chosen else None;out['signature']=sig
    if not sig:out['reason']='unavailable_non_noun_unknown_or_number_analysis'
    else:
     matches=pools['train'][x['key']].get(enc(sig),{});retained=pools['all_retained'][x['key']].get(enc(sig),{});out['train_supported_faces']={f:sorted(ids) for f,ids in matches.items()};out['all_retained_supported_faces']={f:sorted(ids) for f,ids in retained.items()}
     if len(matches)==1:out['target']=next(iter(matches));out['reason']='exact_train_supported_form'
     elif len(matches)>1:out['reason']='ambiguous_supported_faces'
     elif retained:out['reason']='off_training_pool_retained_elsewhere'
     else:out['reason']='new_or_unsupported_lexical_candidate'
   out['agrees_reference']=out['target'] in x['targets'] if out['target'] else False;out['zero_immersion']=out['target'] is not None and norm(out['target'])==json.loads(x['key'])[0];row['methods'][method]=out
  row['lrx_changes_first_analysis']=row['mapped'] and row['methods']['bilingual_default'].get('chosen_analysis')!=row['methods']['lexical_selection'].get('chosen_analysis');row['changes_supported_face']=row['methods']['bilingual_default']['target']!=row['methods']['lexical_selection']['target'];rows.append(row)
 summary={'cohort':len(rows),'unique_endpoints':len(allkeys),'reused_development_endpoints':len(maps.keys()&json.loads((R/'qualify/endpoint-mapping.json').read_text()).keys()),'mapped':sum(x['mapped'] for x in rows),'lrx_changes_first_analysis':sum(x['lrx_changes_first_analysis'] for x in rows),'changes_supported_face':sum(x['changes_supported_face'] for x in rows),'methods':{},'not_fresh_benchmark':True}
 nb={x['id']:x for x in json.loads((N/'compare/predictions.json').read_text()) if x['pool']=='explicit' and x['split']=='test'};assert set(nb)=={x['id'] for x in rows}
 for method in ('bilingual_default','lexical_selection'):
  summary['methods'][method]={'reasons':dict(collections.Counter(x['methods'][method]['reason'] for x in rows)),'predicted':sum(x['methods'][method]['target'] is not None for x in rows),'reference_agreement':sum(x['methods'][method]['agrees_reference'] for x in rows),'zero_immersion':sum(x['methods'][method]['zero_immersion'] for x in rows),'differs_from_nb_default':sum(x['methods'][method]['target']!=nb[x['id']]['methods']['default']['target'] for x in rows)}
 joint=[x for x in rows if all(z['target'] is not None for z in x['methods'].values())];summary['joint_supported']={'denominator':len(joint),'reference_agreement':{method:sum(x['methods'][method]['agrees_reference'] for x in joint) for method in ('bilingual_default','lexical_selection')},'gains':sum(x['methods']['lexical_selection']['agrees_reference'] and not x['methods']['bilingual_default']['agrees_reference'] for x in joint),'losses':sum(not x['methods']['lexical_selection']['agrees_reference'] and x['methods']['bilingual_default']['agrees_reference'] for x in joint)}
 r.save('endpoint-mapping.json',maps);r.save('predictions.json',rows);r.save('metrics.json',summary)
 # No reference agreement or semantic outcome affects selection; prior16 whole components excluded.
 exposed_components={x['component'] for x in xs if x['id'] in exposed};eligible=[x for x in rows if x['component'] not in exposed_components and x['lrx_changes_first_analysis']];eligible=sorted(eligible,key=lambda x:digest(['apertium-lrx-review-r01',x['id']]));selected=[];seen=set()
 for x in eligible:
  if x['component'] in seen:continue
  selected.append(x);seen.add(x['component'])
  if len(selected)==12:break
 byid={x['id']:x for x in xs};packet=[];key=[]
 for i,x in enumerate(selected,1):
  original=byid[x['id']];e=d['endpoints'][x['endpoint']];tok=e['tokens'][original['focus_index']];a,b=tok['codepoints'];targets=sorted({z['target'] for z in x['methods'].values()},key=lambda t:digest(['lrx-blind-option-r01',x['id'],t]));options=[{'option_id':chr(65+j),'target':t,'mixed_output':e['text'] if t is None else e['text'][:a]+t+e['text'][b:],'zero_immersion':t is None or norm(t)==norm(tok['text'])} for j,t in enumerate(targets)];cid='lrx-'+str(i).zfill(3);packet.append({'case_id':cid,'source_focus_id':x['id'],'source':e,'focus_utf16':x['source_span'],'options':options,'full_parallel_witnesses':{pid:d['pairs'][pid] for pid in original['pair_ids']},'policy':'Exact one-focus mixed output; unavailable choice leaves source unchanged with zero immersion; no full sentence grammar translation.'});key.append({'case_id':cid,'prediction_id':x['id'],'methods':{method:next(o['option_id'] for o in options if o['target']==z['target']) for method,z in x['methods'].items()}})
 r.save('review-selection-freeze.json',{'eligible_new_components':len({x['component'] for x in eligible}),'eligible_records':len(eligible),'selected':[x['id'] for x in selected],'excluded_review16_components':sorted(exposed_components),'max':12,'no_backfill':True,'prior_exposures_already_quarantined_by_original_split':True});r.save('blind-review-packet.json',{'cases':packet,'methods_present':False,'reused_exposed_benchmark':True,'fresh_review_sources':'Previously held-out sources excluding all prior exposed components and prior16 NB reviewed components; this is not a new benchmark split.'});r.save('review-method-key.json',key);db.close();r.receipt['summary']=summary

def main():
 r=Run(sys.argv[1])
 try:{'qualify':qualify,'cohort':cohort}[sys.argv[1]](r);r.finish()
 except BaseException as e:r.finish(repr(e));raise
if __name__=='__main__':main()
