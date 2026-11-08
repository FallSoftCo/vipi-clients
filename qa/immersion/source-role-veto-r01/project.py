#!/usr/bin/env python3
"""Frozen fixed-pool role ablation. Execute only after structural review."""
import collections,functools,gzip,hashlib,importlib.util,json,os,pathlib,resource,shutil,signal,sqlite3,time,unicodedata
HERE=pathlib.Path(__file__).resolve().parent
BASE=pathlib.Path('/home/ai/Development/investigations')
INPUT=BASE/'vipi-source-role-veto-20261108-r01/inputs.json'
APPLE=BASE/'vipi-apple-delivery-20261107-r01/source-role-veto-r01/outputs.jsonl'
OPENNLP=BASE/'vipi-source-role-veto-20261108-r01/android/annotations.jsonl'
ORDER=BASE/'vipi-immersion-reconciliation-20261107-r01/scaled-mechanism-cases-r01/editorial-runtime-candidate-r03.json'
EXPECTED={'comparison-protocol.json':'f4f22f184a7f05bc7fea15d17fd028951e38b7795d6afdd7818ffa36d98d145b','review-selection.json':'afe0dc84f52d41529be1ade124e529bdc748b694103ac0009ea392584b50b305'}
ARM_NAMES=['original','eligible_links','apple_disagreement_veto','apple_role_required','opennlp_disagreement_veto','opennlp_role_required']
def encoded(x):return json.dumps(x,ensure_ascii=False,separators=(',',':'),sort_keys=True)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def norm(x):return ' '.join(unicodedata.normalize('NFC',x).casefold().split())
def vm():return {k:int(v.split()[0])*1024 for k,v in (l.split(':',1) for l in pathlib.Path('/proc/self/status').read_text().splitlines() if l.startswith(('VmHWM:','VmPeak:','VmRSS:')))}
def write(p,x):
 with p.open('x') as f:f.write(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def load_module(name,p):
 spec=importlib.util.spec_from_file_location(name,p);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def annotations(path,engine,sources):
 result={};ordered=[];repeat_count=0;first20={}
 with path.open() as f:
  for line in f:
   row=json.loads(line);ident=row['id'];assert ident in sources
   text=sources[ident];raw=text.encode('utf-16-le');assert row['source_sha256']==hashlib.sha256(text.encode()).hexdigest()
   if engine=='opennlp' and row['pass']==1:
    assert ordered==list(sources) and repeat_count<20
    assert ident==ordered[repeat_count]
    assert (row['source_sha256'],row['tokens'])==first20[ident]
    repeat_count+=1;continue
   assert repeat_count==0 and ident not in result
   ordered.append(ident)
   if engine=='apple':assert row['utf16_length']==len(raw)//2 and not row['missing_scheme']
   else:
    assert row['pass']==0
    if len(ordered)<=20:first20[ident]=(row['source_sha256'],row['tokens'])
   tokens={};end=0
   for a,b,tag,score in row['tokens']:
    if engine=='apple':b=a+b
    assert isinstance(a,int) and isinstance(b,int) and end<=a<b<=len(raw)//2
    assert not raw[2*end:2*a].decode('utf-16-le').strip()
    assert raw[2*a:2*b].decode('utf-16-le').strip()
    assert (a,b) not in tokens;tokens[a,b]=(tag,score);end=b
   assert not raw[2*end:].decode('utf-16-le').strip();result[ident]=tokens
 assert ordered==list(sources) and set(result)==set(sources)
 assert repeat_count==(20 if engine=='opennlp' else 0)
 return result

def metadata(catalog_path,unit_path):
 db=sqlite3.connect(unit_path.as_uri()+'?mode=ro&immutable=1',uri=True);db.execute('PRAGMA cache_size=-8192')
 @functools.lru_cache(maxsize=32)
 def units(language,key):
  r=db.execute('SELECT evidence FROM units WHERE language=? AND key=?',(language,key)).fetchone();assert r is not None
  return json.loads(r[0])
 result={}
 with gzip.open(catalog_path,'rt') as f:
  for line in f:
   cat=json.loads(line)
   if (cat['choice_kind'],cat['arm'])!=('dictionary_complete','grow-diag-final-and'):continue
   cid=cat['catalog_id'];assert cid not in result
   source=units('en',cat['source_key']);target=units(cat['pair'].split('-')[1],cat['target_key']);links=[];rejections=collections.Counter()
   for s in source:
    for t in target:
     for st in s['terms']:
      for tt in t['terms']:
       if st['sense_id']!=tt['sense_id']:continue
       reasons=[]
       if not st['eligible']:reasons.append('source_term_ineligible')
       if not tt['eligible']:reasons.append('target_term_ineligible')
       if not t['target_safe']:reasons.append('target_form_unsafe')
       if reasons:rejections.update(reasons);continue
       # Deliberately no explicit/source_safe/targetPOS/number equality filter.
       links.append({'sense_id':st['sense_id'],'source_pos':s['pos'],'source_lexeme':s['lexeme_id'],'source_surface':s['surface'],'source_number':s['number'],'source_features':s['features'],'source_term_explicit':st['explicit'],'source_term_eligible':st['eligible'],'source_sense_url':st['sense_source_url'],'source_label':st['label'],'target_pos':t['pos'],'target_lexeme':t['lexeme_id'],'target_surface':t['surface'],'target_number':t['number'],'target_features':t['features'],'target_reading':tt['reading'],'target_term_explicit':tt['explicit'],'target_term_eligible':tt['eligible'],'target_safe':t['target_safe'],'target_sense_url':tt['sense_source_url']})
   shared=cat['shared_sense_ids'];shared=json.loads(shared) if isinstance(shared,str) else shared
   assert {link['sense_id'] for link in links}<=set(shared),(cid,'eligible link outside catalog shared senses')
   result[cid]={'pair':cat['pair'],'source_key':cat['source_key'],'target_key':cat['target_key'],'target_face':cat['target_face'],'eligible':bool(links),'linked_source_POS':sorted({x['source_pos'] for x in links}),'eligible_links':links,'ineligible_link_reason_counts':dict(rejections),'catalog_evidence':{k:cat[k] for k in ['id','pair_id','provenance','source_context','target_face','source_context_tokens','target_context_tokens','distinct_components','observations','mean_lexical_score']}}
 db.close();units.cache_clear();return result

def role(candidate,meta,tokens,mapping):
 evidence=tokens.get(tuple(candidate['focus_utf16']))
 if evidence is None:return {'status':'unassessed','reason':'no_exact_single_annotation_token','raw_tag':None,'raw_score':None,'mapped':None}
 tag,score=evidence;mapped=mapping.get(tag)
 if mapped is None:return {'status':'unassessed','reason':'unmapped_tag','raw_tag':tag,'raw_score':score,'mapped':None}
 return {'status':'compatible' if mapped in meta['linked_source_POS'] else 'conflict','reason':'source_role_comparison','raw_tag':tag,'raw_score':score,'mapped':mapped}

def choose(selector,candidates,words,protected,masks,known,order):
 indices=[i for i,c in candidates];chosen=selector.select([c for i,c in candidates],words,protected,masks,.25,known,order)
 return {**{k:[indices[i] for i in chosen[k]] for k in ['selected_indices','pre_budget_indices','budget_only_indices']},'rejected':[dict(r,index=indices[r['index']]) for r in chosen['rejected']],'budget':chosen['budget']}

def run():
 started=time.monotonic();protocol=json.loads((HERE/'comparison-protocol.json').read_text());policy=json.loads((HERE/'review-selection.json').read_text());limits=protocol['resource_limits'];out=pathlib.Path(limits['output_directory'])
 os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});resource.setrlimit(resource.RLIMIT_AS,(limits['max_address_space_bytes'],)*2)
 def timeout(*a):raise TimeoutError('450 second projection bound')
 signal.signal(signal.SIGALRM,timeout);signal.alarm(limits['max_seconds'])
 assert shutil.disk_usage(out.parent).free>=limits['minimum_free_bytes']+limits['maximum_added_output_bytes']
 out.mkdir(exist_ok=False)
 def guard():
  assert sum(p.stat().st_size for p in out.rglob('*') if p.is_file())<=limits['maximum_added_output_bytes']
  assert shutil.disk_usage(out).free>=limits['minimum_free_bytes']
  assert time.monotonic()-started<limits['max_seconds']
 try:
  for name,digest in EXPECTED.items():assert sha(HERE/name)==digest
  bindings={**protocol['input_bindings'],**policy['input_bindings']}
  for record in bindings.values():assert sha(pathlib.Path(record['path']))==record['sha256']
  extra={str(INPUT):protocol['source_input_sha256'],str(APPLE):'4dbcfbd81b0a5aadd9fec3374207b5ab85015aed9a41bcb3221b2a5b47e5eef7',str(OPENNLP):'d74ad01af3d62c969993a96f2c10d51ad6a25986af2e5b8cbf8e9711c61776fe',str(ORDER):'38a5c9989baa7603d5caf2bb03c2ca38021b56e0cba871a1b4b16e4de98aedc1'}
  extra[str(HERE.parent/'conversation_corpus.py')]='9e7f8f2424122ace65ba0d0cdbd0191c2e7a1d2c496e443428b2a6e56c24bcd7'
  for p,digest in extra.items():assert sha(pathlib.Path(p))==digest
  freeze={'production':False,'before_projection_outputs':True,'contracts':EXPECTED,'inputs':bindings,'additional_input_hashes':extra,'code_hashes':{p.name:sha(p) for p in [pathlib.Path(__file__),HERE/'assemble_review.py']},'limits':limits,'annotation_coordinates':{'apple':'start,length','opennlp':'start,end'},'learned_family_order':'unchanged frozen R03 control order','baseline_strategy':'Reproduce every complete_grow decision for all9535sources/2pairs/5known first; cache only complete_grow subset before ablations.'}
  write(out/'execution-freeze.json',freeze)
  sources_list=json.loads(INPUT.read_text())['cases'];sources={r['id']:r['text'] for r in sources_list};assert len(sources)==len(sources_list)==9535
  annotation={engine:annotations(p,engine,sources) for engine,p in [('apple',APPLE),('opennlp',OPENNLP)]}
  write(out/'annotation-verification.json',{'complete':True,'sources':len(sources),'original_text_hash_and_ranges_verified':True,'token_counts':{k:sum(map(len,v.values())) for k,v in annotation.items()},'measurement':vm()})
  selector=load_module('frozen_selector',pathlib.Path(bindings['selector']['path']));order=json.loads(ORDER.read_text())['learned_family_order']
  trace=pathlib.Path(bindings['baseline_trace']['path']);cache=out/'complete-baseline-cache.jsonl.gz';seen=set();decisions_verified=0
  # No ablated decisions are produced until this full baseline pass succeeds.
  with gzip.open(trace,'rt') as stream,gzip.open(cache,'xt',compresslevel=3) as dest:
   for line in stream:
    row=json.loads(line);ident=row['id'];assert ident in sources and ident not in seen and row['text']==sources[ident];seen.add(ident)
    small={k:row[k] for k in ['id','text','native_words_utf16','source_masks','protected_ranges_utf16']};small['pairs']={}
    for pair in protocol['pairs']:
     data=row['pairs'][pair];candidates=[(i,c) for i,c in enumerate(data['candidates']) if c['kind']=='complete_grow'];baseline={}
     for i,c in candidates:
      assert selector.project_scope(row['text'],row['native_words_utf16'],c['focus_utf16'])=={'cost':c['cost'],'codepoints':c['output_codepoints']}
      raw=row['text'].encode('utf-16-le');a,b=c['focus_utf16'];assert raw[2*a:2*b].decode('utf-16-le')==c['source']
     original={(a,d,k):t for a,d,k,t in data['decisions']}
     for known in protocol['known_states']:
      actual=choose(selector,candidates,row['native_words_utf16'],row['protected_ranges_utf16'],row['source_masks'],known,order)
      expected=data['decision_table'][original['complete_grow',.25,known]];assert actual==expected,(ident,pair,known,'baseline mismatch')
      baseline[known]=actual;decisions_verified+=1
     small['pairs'][pair]={'candidates':candidates,'baseline':baseline}
    dest.write(encoded(small)+'\n')
    if len(seen)%250==0:guard()
  assert seen==set(sources);write(out/'baseline-reproduction.json',{'complete':True,'sources':len(seen),'exact_full_decisions_verified':decisions_verified,'all_fields_compared':['selected_indices','pre_budget_indices','budget_only_indices','rejected','budget'],'cache_sha256':sha(cache),'seconds':time.monotonic()-started,'measurement':vm()})
  metas=metadata(pathlib.Path(bindings['catalog']['path']),pathlib.Path(bindings['units']['path']));write(out/'catalog-link-evidence.json',metas);guard()
  assemble=load_module('review_assembler',HERE/'assemble_review.py');review=assemble.Selection(policy,bindings,sources)
  summary=collections.defaultdict(collections.Counter);rows=0;decision_path=out/'decisions.jsonl.gz'
  with gzip.open(cache,'rt') as stream,gzip.open(decision_path,'xt',compresslevel=3) as dest:
   for line in stream:
    row=json.loads(line);ident=row['id'];n=len(row['native_words_utf16']);compact={'id':ident,'pairs':{}}
    for pair,data in row['pairs'].items():
     candidates=data['candidates'];cmap=dict(candidates);status={};members={a:[] for a in ARM_NAMES}
     for i,c in candidates:
      meta=metas[c['catalog_id']];assert (meta['pair'],meta['source_key'],meta['target_face'])==(pair,c['source_key'],c['target'])
      assert norm(c['target'])==meta['target_key']
      evidence={e:role(c,meta,annotation[e][ident],protocol['POS_map'][e]) for e in ['apple','opennlp']}
      status[i]={'eligible':meta['eligible'],**evidence};members['original'].append((i,c))
      if not meta['eligible']:continue
      members['eligible_links'].append((i,c))
      for e in ['apple','opennlp']:
       if evidence[e]['status']!='conflict':members[e+'_disagreement_veto'].append((i,c))
       if evidence[e]['status']=='compatible':members[e+'_role_required'].append((i,c))
     records={}
     for known in protocol['known_states']:
      byarm={}
      for arm in ARM_NAMES:
       selected=data['baseline'][known] if arm=='original' else choose(selector,members[arm],row['native_words_utf16'],row['protected_ranges_utf16'],row['source_masks'],known,order)
       byarm[arm]=selected;chosen=[cmap[i] for i in selected['selected_indices']];s=summary[pair+'|'+arm+'|'+known]
       s['messages']+=1;s['source_words']+=n;s['pool_candidates']+=len(candidates);s['admitted_arm_candidates']+=len(members[arm]);s['metadata_ineligible_candidates']+=sum(not v['eligible'] for v in status.values());s['arm_filter_rejected_candidates']+=len(candidates)-len(members[arm])
       engine=arm.split('_')[0]
       if engine in annotation:
        for v in status.values():
         if v['eligible']:s['eligible_candidate_role_'+v[engine]['status']]+=1
       s['displayed_messages']+=bool(chosen);s['content_messages']+=any(c['category']=='content' for c in chosen);s['function_only_messages']+=bool(chosen) and all(c['category']=='function' for c in chosen);s['unresolved_only_messages']+=bool(chosen) and not any(c['category']=='content' for c in chosen) and any(c['category']=='unresolved' for c in chosen);s['changed_words']+=sum(c['cost'] for c in chosen);s['content_anchor_words']+=sum(c['content_anchor_native_words'] for c in chosen);s['prebudget_available_messages']+=bool(selected['pre_budget_indices'])
       base=data['baseline'][known]['selected_indices'];sel=selected['selected_indices'];s['changed_output_vs_original_messages']+=sel!=base;s['added_vs_original_scopes']+=len(set(sel)-set(base));s['removed_vs_original_scopes']+=len(set(base)-set(sel))
      base=byarm['original']['selected_indices'];control=byarm['eligible_links']['selected_indices']
      records[known]={a:{'selected_indices':d['selected_indices'],'added_vs_original':sorted(set(d['selected_indices'])-set(base)),'removed_vs_original':sorted(set(base)-set(d['selected_indices'])),'added_vs_eligible':sorted(set(d['selected_indices'])-set(control)),'removed_vs_eligible':sorted(set(control)-set(d['selected_indices']))} for a,d in byarm.items()}
      review.consider(ident,pair,known,byarm,cmap)
     compact['pairs'][pair]={'candidate_decisions':status,'decisions':records}
    dest.write(encoded(compact)+'\n');rows+=1
    if rows%250==0:guard()
  metrics={k:dict(v,changed_word_depth=v['changed_words']/v['source_words'] if v['source_words'] else 0,content_anchor_depth=v['content_anchor_words']/v['source_words'] if v['source_words'] else 0) for k,v in summary.items()};write(out/'metrics.json',metrics)
  selection=review.freeze(out);guard()
  assemble.packet(out,selection,cache,decision_path,metas,annotation,protocol,bindings,selector,order);guard()
  receipt={'complete':True,'production':False,'semantic_approval':False,'rows':rows,'baseline_decisions_verified':decisions_verified,'review_cases':len(selection['selected']),'seconds':time.monotonic()-started,'measurement':vm(),'limits':limits,'outputs':{p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in out.iterdir() if p.is_file()}}
  write(out/'receipt.json',receipt);write(HERE/'projection-receipt.json',receipt);print(encoded(receipt),flush=True)
 except BaseException as exc:
  failure={'complete':False,'production':False,'error':repr(exc),'seconds':time.monotonic()-started,'measurement':vm(),'files':{p.name:p.stat().st_size for p in out.iterdir() if p.is_file()}}
  write(out/'failure-receipt.json',failure);print(encoded(failure),flush=True);raise
if __name__=='__main__':run()
