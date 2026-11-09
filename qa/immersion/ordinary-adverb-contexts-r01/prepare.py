"""Compact retained ADV support and native candidate overlap; never selects outputs."""
import ast,collections,gzip,hashlib,importlib.util,json,os,pathlib,resource,shutil,signal,socket,sqlite3,sys,time,types
from contract import base_reasons,term_reasons,controls,norm
R=pathlib.Path('/srv/fallsoft/staging/vipi-ordinary-adverb-contexts-20261109-r01');M=1024**2
def enc(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(x):return hashlib.sha256(enc(x).encode()).hexdigest()
def sha(p):
 with open(p,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def db(p):
 d=sqlite3.connect(pathlib.Path(p).as_uri()+'?mode=ro&immutable=1',uri=True);d.execute('PRAGMA query_only=ON');d.execute('PRAGMA cache_size=-8192');return d
def endpoint(e):return hashlib.sha256(json.dumps([e['language'],e['id'],e['text'],e['tokens']],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
class Run:
 def __init__(self,stage):
  assert socket.gethostname()=='fallsoft-production-20261106';self.start=time.monotonic();self.stage=stage;self.p=json.loads((R/'protocol.json').read_text());self.out=R/stage;self.out.mkdir(exist_ok=False);self.r={'complete':False,'stage':stage,'protocol_sha256':sha(R/'protocol.json')};os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});os.nice(10);resource.setrlimit(resource.RLIMIT_AS,(1024**3,)*2);signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('120s')));signal.alarm(120)
 def path(self,k):return pathlib.Path(self.p['inputs'][k]['path'])
 def verify(self):
  self.r['free_bytes']=shutil.disk_usage(R).free;assert self.r['free_bytes']>8*1024**3+48*M
  for n,h in self.p['code_hashes'].items():assert sha(R/n)==h,n
  for k,v in self.p['inputs'].items():assert sha(v['path'])==v['sha256'],k
  assert controls();self.h=load('frozen_heads',self.path('head_helper'));self.common=load('frozen_noun_common',self.path('noun_common'));self.tok=self.common.tokenizer(self.path('tokenizer'));assert self.common.controls(self.tok)
 def write(self,name,v):
  b=(enc(v)+'\n').encode();assert len(b)+sum(p.stat().st_size for p in R.rglob('*') if p.is_file())<32*M,'prospective aggregate cap';(self.out/name).write_bytes(b)
 def prior(self):
  rr=json.loads((R/'corpus/receipt.json').read_text());assert rr['complete'] and rr['protocol_sha256']==sha(R/'protocol.json')
  for n,v in rr['outputs'].items():assert sha(R/'corpus'/n)==v['sha256']
 def finish(self,error=None):
  self.r.update(complete=error is None,error=error,seconds=time.monotonic()-self.start,VmHWM_bytes=int(next(x.split()[1] for x in pathlib.Path('/proc/self/status').read_text().splitlines() if x.startswith('VmHWM:')))*1024,outputs={p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in self.out.iterdir() if p.is_file()});self.write('receipt.json',self.r);print(enc(self.r),flush=True)
def classifier(r):
 env={'json':json,'hashlib':hashlib,'norm':norm,'tokenize':r.tok};tree=ast.parse(r.path('old_projector').read_text());cl=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Producer');method=next(n for n in cl.body if isinstance(n,ast.FunctionDef) and n.name=='classify');exec(compile(ast.Module(body=[method],type_ignores=[]),str(r.path('old_projector')),'exec'),env);init=next(n for n in cl.body if isinstance(n,ast.FunctionDef) and n.name=='__init__');update=next(n for n in ast.walk(init) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='update' and isinstance(n.func.value,ast.Attribute) and n.func.value.attr=='function');base=json.loads(r.path('content_baseline').read_text());control=json.loads(r.path('family_control').read_text());c=types.SimpleNamespace(function={e['source'] for p in base['pairs'].values() for e in p['entries'] if e['category']=='function'}|ast.literal_eval(update.args[0]),roles={k:set(v) for k,v in control['source_roles'].items()},families=control['source_families']);return lambda s:env['classify'](c,s)
def corpus(r):
 r.verify();h=r.h;stream=load('frozen_stream',r.path('stream_helper'));edb=db(r.path('evidence'));tagmap=json.loads(r.path('apertium_protocol').read_text())['tag_to_UPOS'];inventory=json.loads(r.path('endpoint_inventory').read_text())['endpoints'];selected={pid for e in inventory.values() for pid in e['pair_ids']};assert len(selected)==7115;roles=collections.defaultdict(dict)
 for ident,raw in edb.execute("select id,data from objects where kind='lexical_unit'"):
  u=json.loads(raw);rr=[stream.reading_role(a,tagmap) for a in u['contextual_readings']];span=tuple(u['utf16']);assert span not in roles[u['endpoint_key']];roles[u['endpoint_key']][span]={'evidence_id':ident,'chosen_roles':rr,'unknown':any(x in ('UNKNOWN','UNMAPPED_TAG') for x in rr),'joined_morphemes':'UNASSESSABLE_JOINED_MORPHEMES' in rr,'readings':u['contextual_readings']}
 split=json.loads(r.path('split').read_text());exposed=set(split['exposed_components']);newhash=set(json.loads(r.path('review_exclusions').read_text())['hashes']);extra=set();textsplit=collections.defaultdict(set)
 def assign(c):return 'development' if c in exposed else 'test' if int(digest(['contextual-lexical-selection-r01',c])[:16],16)%5==0 else 'train'
 for row in split['rows']:assert assign(row['component'])==row['split']
 with gzip.open(r.path('pairs'),'rt') as f:
  for line in f:
   p=json.loads(line);c=p['source']['component'];textsplit[norm(p['source']['text'])].add(assign(c))
   if hashlib.sha256(('en\0'+norm(p['source']['text'])).encode()).hexdigest() in newhash:extra.add(c)
 assert all(len(s)==1 for s in textsplit.values()),'source normalized cross-split identity'
 dicts={s:db(r.path('dictionary_'+lang)) for s,lang in [('source','en'),('target','es')]};identities={s:h._database_identity(d) for s,d in dicts.items()};rows={};proofs={};forms={};pairs={};endpoints={};rejected=collections.Counter();counts=collections.Counter();rejecthash=hashlib.sha256();processed=set();classify=classifier(r)
 def reject(reason,identity):rejected.update(reason);rejecthash.update((enc([identity,reason])+'\n').encode())
 with gzip.open(r.path('pairs'),'rt') as ps,open(r.path('forward_align')) as fs,open(r.path('reverse_align')) as rs:
  for index,(line,fl,rl) in enumerate(zip(ps,fs,rs,strict=True)):
   p=json.loads(line);assert p['index']==index
   if p['pair_id'] not in selected:continue
   assert p['pair_id'] not in processed;processed.add(p['pair_id']);counts['selected_pairs']+=1;k={s:endpoint(p[s]) for s in dicts};assert all(p['pair_id'] in inventory[e]['pair_ids'] for e in k.values());assert p['source']['component']==p['target']['component']
   focus=[i for i,t in enumerate(p['source']['tokens']) if roles[k['source']].get(tuple(t['utf16']),{}).get('chosen_roles')==['ADV']]
   counts['paired_ADV_tokens']+=len(focus)
   if not focus:continue
   def links(line):
    x={tuple(map(int,v.split('-'))) for v in line.split()};assert all(0<=a<len(p['source']['tokens']) and 0<=b<len(p['target']['tokens']) for a,b in x);return x
   fw,rv=links(fl),links(rl);union=fw|rv;mutual=fw&rv;units={s:h._dictionary_units(dicts[s],p[s]['text'],h._tokens(p[s]['text'],p[s]['tokens']),identities[s]) for s in dicts};suindex={tuple(u['scope']['tokens']):u for u in units['source']}
   for i in focus:
    su=suindex.get((i,i+1));ident=[p['pair_id'],i]
    if not su:reject(['no_complete_source_unit'],ident);continue
    sr=roles[k['source']].get(tuple(su['scope']['utf16']));sf_all=[f for f in su['forms'] if f['pos']=='adv'];counts['paired_source_ADV_forms']+=len(sf_all);category,_,_=classify(su['scope']['text'])
    for sf in sf_all:
     sw=base_reasons(sf,sr)
     if category!='content':sw.append('source_function_classifier')
     if h._maskers(su,units['source']):sw.append('source_enclosing_unit')
     if sw:reject(sw,ident+[sf['form_id']]);continue
     aligned={b for a,b in union if a==i}
     if not aligned:reject(['no_alignment'],ident+[sf['form_id']]);continue
     for tu in units['target']:
      a,b=tu['scope']['tokens']
      if b-a!=1 or a not in aligned:continue
      tr=roles[k['target']].get(tuple(tu['scope']['utf16']))
      for tf in tu['forms']:
       if tf['pos']!='adv':continue
       tw=base_reasons(tf,tr)
       if not any(si==i and a<=ti<b for si,ti in mutual):tw.append('no_mutual_anchor')
       if any((si==i)!=(a<=ti<b) for si,ti in union):tw.append('union_crossing')
       if h._maskers(tu,units['target']):tw.append('target_enclosing_unit')
       if tw:reject(tw,ident+[sf['form_id'],tf['form_id']]);continue
       for st in sf['terms']:
        for tt in tf['terms']:
         if st['sense_id']!=tt['sense_id']:continue
         why=term_reasons(st,tt)
         if why:reject(why,ident+[sf['form_id'],tf['form_id'],st['term_id'],tt['term_id']]);continue
         value={'pair_id':p['pair_id'],'pair_index':index,'component':p['source']['component'],'source_endpoint':k['source'],'target_endpoint':k['target'],'source_scope':su['scope'],'target_scope':tu['scope'],'source_form_id':sf['form_id'],'target_form_id':tf['form_id'],'source_term':st,'target_term':tt,'source_role':sr,'target_role':tr,'forward':sorted(fw),'reverse':sorted(rv),'source_number_not_used':sf['number'],'target_number_not_used':tf['number'],'guards_unchanged':True};ref=digest(value);proofs[ref]=value;forms[sf['form_id']]=sf;forms[tf['form_id']]=tf;pairs[p['pair_id']]=p;endpoints[k['source']]=p['source'];endpoints[k['target']]=p['target'];key=enc([norm(su['scope']['text']),'adv','base']);identity=[p['source']['id'],p['source']['fingerprint'],p['source']['record_sha256'],su['scope']['utf16']];rid=digest([identity,key]);row=rows.setdefault(rid,{'id':rid,'key':key,'source_identity':identity,'endpoint':k['source'],'focus_index':i,'span':su['scope']['utf16'],'component':p['source']['component'],'split':assign(p['source']['component']),'additional_exposure_quarantine':p['source']['component'] in extra,'targets':{}});assert row['endpoint']==k['source'] and row['component']==p['source']['component'];target=row['targets'].setdefault(tu['scope']['text'],set());target.add(ref)
 assert processed==selected
 for row in rows.values():row['targets']={f:sorted(ids) for f,ids in row['targets'].items()}
 train=[x for x in rows.values() if x['split']=='train' and not x['additional_exposure_quarantine']];sizes=collections.Counter((x['key'],x['component']) for x in train);patterns={}
 for row in train:
  e=endpoints[row['endpoint']];values=[norm(t[0]) for t in r.tok(e['text'])];assert [t[0] for t in r.tok(e['text'])]==[t['text'] for t in e['tokens']];weight=1/(sizes[row['key'],row['component']]*len(row['targets']))
  for key,a,b in r.common.windows(row['key'],values,row['focus_index']):
   p=patterns.setdefault(key,{'source_key':row['key'],'tokens':values[a:b],'focus_offset':row['focus_index']-a,'length':b-a,'counts':collections.Counter(),'rows':collections.defaultdict(set),'components':collections.defaultdict(set)})
   for face in row['targets']:p['counts'][face]+=weight;p['rows'][face].add(row['id']);p['components'][face].add(row['component'])
 rules={};patternhash=hashlib.sha256()
 for key,p in sorted(patterns.items()):
  faces=sorted(p['counts'],key=lambda f:(-p['counts'][f],f));winner=faces[0];weight=p['counts'][winner];runner=p['counts'][faces[1]] if len(faces)>1 else 0;why=[]
  if weight<=1.5*runner+1e-12:why.append('tie_or_margin')
  if len(p['components'][winner])<2:why.append('under_two_components')
  v={'id':digest(key),'source_key':p['source_key'],'tokens':p['tokens'],'focus_offset':p['focus_offset'],'length':p['length'],'target':winner,'winner_weight':weight,'runner_weight':runner,'ratio':weight/runner if runner else None,'winner_components':len(p['components'][winner]),'weighted_counts':dict(p['counts']),'support_rows':{f:sorted(ids) for f,ids in p['rows'].items()},'support_components':{f:sorted(ids) for f,ids in p['components'].items()},'reasons':why};patternhash.update((enc([key,v])+'\n').encode())
  links=collections.defaultdict(set)
  for rid in p['rows'][winner]:
   for ref in rows[rid]['targets'][winner]:
    d=proofs[ref];links[enc([d['source_form_id'],d['target_form_id'],d['source_term']['term_id'],d['target_term']['term_id']])].add(ref)
  v['supported_links']={link:sorted(refs) for link,refs in links.items() if len({proofs[ref]['component'] for ref in refs})>=2}
  if not why:rules[key]=v
 support={'rows':rows,'rules':rules,'proofs':proofs,'forms':forms,'pairs':pairs,'endpoints':endpoints};r.write('support.json',support);r.write('summary.json',{'counts':dict(counts),'source_focuses':len(rows),'train_focuses':len(train),'splits':dict(collections.Counter(x['split'] for x in rows.values())),'additional_quarantined_focuses':sum(x['additional_exposure_quarantine'] for x in rows.values()),'patterns':len(patterns),'rules':len(rules),'overlapping_rejections':dict(rejected),'rejected_identity_reason_stream_sha256':rejecthash.hexdigest(),'pattern_census_sha256':patternhash.hexdigest(),'prospective_encoded_support_bytes':(r.out/'support.json').stat().st_size,'selected_pair_bias':True,'no_native_predictions':True});h.clear_unit_cache()
def native_overlap(r):
 r.verify();r.prior();support=json.loads((R/'corpus/support.json').read_text());rules=support['rules'];byword=collections.defaultdict(set)
 for key,rule in rules.items():byword[json.loads(rule['source_key'])[0]].add(rule['source_key'])
 classify=classifier(r);env={'json':json,'hashlib':hashlib};tree=ast.parse(r.path('annotation_loader').read_text());node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='annotations');exec(compile(ast.Module(body=[node],type_ignores=[]),str(r.path('annotation_loader')),'exec'),env);sources={x['id']:x['text'] for x in json.loads(r.path('annotation_inputs').read_text())['cases']};ann=env['annotations'](r.path('annotations'),'opennlp',sources);en=db(r.path('dictionary_en'));identity=r.h._database_identity(en);counts=collections.Counter();rejects=collections.Counter();native=[];seen=[];baseline_hash=hashlib.sha256();matched_messages=set();novel_messages=set();existing_messages=set()
 with gzip.open(r.path('trace'),'rt') as f,gzip.open(r.path('qualified_decisions'),'rt') as g:
  for aa,bb in zip(f,g,strict=True):
   t=json.loads(aa);old=json.loads(bb);assert t['id']==old['id'] and sources[t['id']]==t['text'];seen.append(t['id']);baseline_hash.update((enc(old['qualified'])+'\n').encode());cs=t['candidates'];baseline_indices={i for i,c in enumerate(cs[:t['baseline_candidate_count']]) if not c['filter_reasons']}|{i for gate in old['gates'].values() for i in gate['admitted_indices']};existing={enc([cs[i]['focus_utf16'],cs[i]['target'],cs[i]['reading']]) for i in baseline_indices};existing_focus={tuple(cs[i]['focus_utf16']) for i in baseline_indices};text=t['text'];tokens=r.tok(text);values=[norm(x[0]) for x in tokens];offset=[0]
   for ch in text:offset.append(offset[-1]+len(ch.encode('utf-16-le'))//2)
   words={tuple(x) for x in t['native_words_utf16']};positions=[i for i,x in enumerate(tokens) if norm(x[0]) in byword]
   if not positions:continue
   if len(tokens)>r.h.MAX_SENTENCE_TOKENS or offset[-1]>r.h.MAX_TEXT_UTF16:
    rejects['native_text_exceeds_unchanged_helper_bound']+=len(positions);continue
   geometry=[{'text':v,'codepoints':[a,b],'utf16':[offset[a],offset[b]]} for v,a,b in tokens];units=r.h._dictionary_units(en,text,r.h._tokens(text,geometry),identity);unitindex={tuple(u['scope']['tokens']):u for u in units}
   for i in positions:
    word,a,b=tokens[i];span=[offset[a],offset[b]];counts['potential_native_focuses']+=1;why=[];raw=ann[t['id']].get(tuple(span));category,anchors,knowledge=classify(word);su=unitindex.get((i,i+1))
    if tuple(span) not in words:why.append('not_exact_native_token')
    if not raw or raw[0]!='ADV':why.append('live_source_not_ADV')
    if category!='content':why.append('source_function_classifier')
    if not su:why.append('no_complete_native_unit')
    elif r.h._maskers(su,units):why.append('native_enclosing_unit')
    if any(x<span[1] and span[0]<y for x,y in t['protected_ranges_utf16']):why.append('native_protected_range')
    if any(m['utf16'][0]<=span[0] and span[1]<=m['utf16'][1] and m['utf16']!=span for m in t['source_masks']):why.append('retained_enclosing_mask')
    if why:rejects.update(why);continue
    # Current source form and term guards remain authoritative at this exact occurrence.
    sf={f['form_id']:f for f in su['forms'] if f['pos']=='adv' and f['complete'] and f['mode'] in (1,2) and not f['reasons'] and not f['features'] and norm(f['surface'])==norm(f['headword'])};matches=[]
    for sourcekey in byword[norm(word)]:
     for rulekey,left,right in r.common.windows(sourcekey,values,i):
      rule=rules.get(rulekey)
      if not rule:continue
      if any((offset[tokens[j][1]],offset[tokens[j][2]]) not in words for j in range(left,right)):continue
      links=[];readings=set();proofrefs=set()
      for link,refs in rule['supported_links'].items():
       sid,tid,st,tt=json.loads(link)
       if sid not in sf or not any(x['term_id']==st and not x['reasons'] and x['eligible'] and x['explicit'] for x in sf[sid]['terms']):continue
       links.append(link);proofrefs.update(refs)
       for ref in refs:
        d=support['proofs'][ref];assert d['target_scope']['text']==rule['target'];reading=d['target_term']['reading']
        if reading:readings.add(reading)
      if not links:rejects['rule_without_exact_supported_native_form_term']+=1;continue
      if norm(word)==norm(rule['target']):rejects['identical_face_zero_immersion']+=1;continue
      identitykey=enc([span,rule['target'],sorted(readings)]);matches.append({'rule_id':rule['id'],'context_utf16':[offset[tokens[left][1]],offset[tokens[right-1][2]]],'source_tokens':[left,right],'target':rule['target'],'reading':sorted(readings),'support_links':sorted(links),'proof_refs':sorted(proofrefs),'already_current_candidate':identitykey in existing,'focus_already_current_candidate':tuple(span) in existing_focus})
    if matches:
     matched_messages.add(t['id']);counts['native_focuses_with_qualified_matches']+=1;counts['matched_rule_occurrences']+=len(matches);identities={enc([span,m['target'],m['reading']]) for m in matches};novel=identities-existing;counts['novel_candidate_identities']+=len(novel);counts['existing_candidate_identities']+=len(identities&existing)
     if novel:novel_messages.add(t['id'])
     if identities&existing:existing_messages.add(t['id'])
     native.append({'id':t['id'],'focus_utf16':span,'source':word,'role':list(raw),'category':category,'content_anchor_words':anchors,'knowledge_ids':knowledge,'mask_sha256':digest([t['source_masks'],t['protected_ranges_utf16']]),'matches':matches})
 assert seen==list(sources) and len(seen)==9535;r.write('native-overlap.json',{'native_focuses':native,'baseline_source_trace_sha256':r.p['inputs']['trace']['sha256'],'qualified_baseline_sha256':r.p['inputs']['qualified_decisions']['sha256'],'baseline_decision_stream_sha256':baseline_hash.hexdigest(),'no_selector_or_new_prediction':True});r.write('summary.json',{'counts':dict(counts),'messages':9535,'matched_messages':len(matched_messages),'messages_with_novel_candidates':len(novel_messages),'messages_with_existing_candidates':len(existing_messages),'overlapping_rejections':dict(rejects),'exact_encoded_overlap_bytes':(r.out/'native-overlap.json').stat().st_size,'zero_novel_gain':not novel_messages,'qualification':'Potential candidates only. Existing baseline bytes untouched. Longest-first and budget choices have not run.'});r.h.clear_unit_cache()
if __name__=='__main__':
 stage=sys.argv[1];assert stage in ['corpus','native-overlap'];r=Run(stage)
 try:(corpus if stage=='corpus' else native_overlap)(r);r.finish()
 except BaseException as e:r.finish(repr(e));raise
