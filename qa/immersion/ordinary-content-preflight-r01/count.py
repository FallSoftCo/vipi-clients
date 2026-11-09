"""Count exact prospective records only; frozen helpers and original reasons unchanged."""
import collections,gzip,hashlib,importlib.util,json,os,pathlib,resource,shutil,signal,socket,time
R=pathlib.Path('/srv/fallsoft/staging/vipi-ordinary-content-preflight-20261109-r01');M=1024**2
import sqlite3

def enc(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def sha(p):
 with open(p,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def db(p):
 d=sqlite3.connect(pathlib.Path(p).as_uri()+'?mode=ro&immutable=1',uri=True);d.execute('PRAGMA query_only=ON');d.execute('PRAGMA cache_size=-8192');return d

def main():
 assert socket.gethostname()=='fallsoft-production-20261106';start=time.monotonic();os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});os.nice(10);resource.setrlimit(resource.RLIMIT_AS,(1024**3,)*2);signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('120s bound')));signal.alarm(120);p=json.loads((R/'protocol.json').read_text());assert sha(__file__)==p['code_sha256'];out=R/'outputs';out.mkdir(exist_ok=False);receipt={'complete':False,'protocol_sha256':sha(R/'protocol.json'),'free_bytes':shutil.disk_usage(R).free};assert receipt['free_bytes']>8*1024**3+8*M
 counts=collections.Counter();reasons=collections.Counter();classes=collections.Counter();features=collections.Counter();sizes=collections.Counter();seen=set();relation_ids=set();row_sizes=[];phase_occ=collections.defaultdict(set);focus_alternatives=collections.defaultdict(set)
 try:
  for k,v in p['inputs'].items():assert sha(v['path'])==v['sha256'],k
  path=lambda k:p['inputs'][k]['path'];h=load('frozen_heads',path('head_helper'));stream=load('frozen_stream',path('stream_helper'));rolehelper=load('frozen_role',path('role_helper'));assert rolehelper.mechanism_controls()['passed'];edb=db(path('evidence'));existing={x[0] for x in edb.execute('select id from objects')};inventory=json.loads(pathlib.Path(path('endpoint_inventory')).read_text());endpoints=inventory['endpoints'];selected={v for e in endpoints.values() for v in e['pair_ids']};assert len(selected)==7115;rawroles=collections.defaultdict(list);tagmap=json.loads(pathlib.Path(path('apertium_protocol')).read_text())['tag_to_UPOS']
  for ident,text in edb.execute("select id,data from objects where kind='lexical_unit'"):
   u=json.loads(text);roles=[stream.reading_role(a,tagmap) for a in u['contextual_readings']];rawroles[u['endpoint_key']].append({'utf16':u['utf16'],'evidence_id':ident,'chosen_roles':roles,'unknown':any(r in ('UNKNOWN','UNMAPPED_TAG') for r in roles),'joined_morphemes':'UNASSESSABLE_JOINED_MORPHEMES' in roles,'readings':u['contextual_readings']})
  dicts={side:db(path('dictionary_'+lang)) for side,lang in [('source','en'),('target','es')]};identities={s:h._database_identity(d) for s,d in dicts.items()};direct=json.loads(pathlib.Path(path('direct_relations')).read_text())['relations'];assert len(direct)==17
  def remember(kind,value):
   data=enc(value);ident=hashlib.sha256(enc([kind,value]).encode()).hexdigest()
   if ident not in seen:
    seen.add(ident);n=len(data.encode())+len(ident)+len(kind);sizes[kind+'_unique_rows']+=1;sizes[kind+'_logical_bytes']+=n
    if ident in existing:sizes['existing_objects_reused']+=1;sizes['existing_logical_bytes_reused']+=n
    else:sizes['new_objects']+=1;sizes['new_logical_bytes']+=n
   return ident
  def unitref(k,u):return remember('dictionary_unit',{'endpoint_key':k,'unit':{a:b for a,b in u.items() if a!='forms'},'form_evidence_refs':[remember('dictionary_form',f) for f in u['forms']]})
  def endpointkey(e):return hashlib.sha256(json.dumps([e['language'],e['id'],e['text'],e['tokens']],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
  def links(line,pair):
   x={tuple(map(int,v.split('-'))) for v in line.split()};assert all(0<=a<len(pair['source']['tokens']) and 0<=b<len(pair['target']['tokens']) for a,b in x);return x
  def save_relation(v):
   ident=remember('prospective_relation',v);assert ident not in relation_ids;relation_ids.add(ident);n=len(enc(v).encode());row_sizes.append(n);sizes['relation_index_payload_bytes']+=len(ident)+len(v['pair_id'])+len(v['stratum']);counts['relation_rows']+=1
  processed=set()
  with gzip.open(path('pairs'),'rt') as ps,open(path('forward_align')) as fs,open(path('reverse_align')) as rs:
   for index,(line,fl,rl) in enumerate(zip(ps,fs,rs,strict=True)):
    pair=json.loads(line);assert pair['index']==index
    if pair['pair_id'] not in selected:continue
    assert pair['pair_id'] not in processed;processed.add(pair['pair_id']);counts['selected_pairs']+=1;k={s:endpointkey(pair[s]) for s in ['source','target']};assert all(x in endpoints for x in k.values());assert all(pair['pair_id'] in endpoints[x]['pair_ids'] for x in k.values());assert pair['source']['component']==pair['target']['component'];fw=links(fl,pair);rv=links(rl,pair);union=fw|rv;mutual=fw&rv;units={s:h._dictionary_units(dicts[s],pair[s]['text'],h._tokens(pair[s]['text'],pair[s]['tokens']),identities[s]) for s in k};rolemap={s:{tuple(u['utf16']):u for u in rawroles[k[s]]} for s in k};source_units={tuple(u['scope']['tokens']):u for u in units['source']};target_units=units['target'];mapped={'NOUN':'noun','VERB':'verb','ADJ':'adj','ADV':'adv'}
    for i,tok in enumerate(pair['source']['tokens']):
     lu=rolemap['source'].get(tuple(tok['utf16']));actual=lu['chosen_roles'][0] if lu and len(lu['chosen_roles'])==1 and not lu['unknown'] and not lu['joined_morphemes'] else None
     if actual not in mapped:continue
     pos=mapped[actual];occ=enc([k['source'],tok['utf16']]);phase_occ[(pos,'role_potential')].add(occ);counts['paired_potential_'+pos]+=1;su=source_units.get((i,i+1))
     if su is None:phase_occ[(pos,'no_source_unit')].add(occ);continue
     srref=unitref(k['source'],su)
     if su['guard']:classes[(pos,'source_guard',su['guard']['reason'])]+=1
     scopeforms=[f for f in su['forms'] if f['pos']==pos];counts['source_form_alternatives_'+pos]+=len(scopeforms)
     for sf in scopeforms:
      for reason in sf['reasons']:reasons[('source_form',pos,reason)]+=1
      features[('source',pos,enc(sf['features']))]+=1
     if not scopeforms:phase_occ[(pos,'no_source_POS_form')].add(occ)
     if not any(f['complete'] and f['mode'] in (1,2) for f in scopeforms):phase_occ[(pos,'no_complete_supported_source_form')].add(occ)
     aligned=sorted({b for a,b in union if a==i})
     if not aligned:phase_occ[(pos,'no_alignment')].add(occ);continue
     ta,tb=aligned[0],aligned[-1]+1;envelope=[pair['target']['tokens'][ta]['utf16'][0],pair['target']['tokens'][tb-1]['utf16'][1]];tus=[u for u in target_units if ta<=u['scope']['tokens'][0]<u['scope']['tokens'][1]<=tb];counts['target_units_in_envelope_'+pos]+=len(tus)
     if not tus:phase_occ[(pos,'no_target_unit_in_envelope')].add(occ)
     target_terms=collections.defaultdict(list);target_forms=[]
     for tu in tus:
      trref=unitref(k['target'],tu)
      for tf in tu['forms']:
       target_forms.append((tu,tf,trref));features[('target',tf['pos'],enc(tf['features']))]+=1
       for tt in tf['terms']:target_terms[tt['sense_id']].append((tu,tf,tt,trref))
     if not any(tf['pos']==pos and tf['complete'] and tf['mode'] in (1,2) for _,tf,_ in target_forms):phase_occ[(pos,'no_complete_target_POS_form')].add(occ)
     source_masks=h._maskers(su,units['source']);anylink=False;done_direct=set()
     for sf in su['forms']:
      for st in sf['terms']:
       for tu,tf,tt,trref in target_terms.get(st['sense_id'],[]):
        anylink=True;stratum='old_explicit_shared_link' if st['explicit'] and tt['explicit'] else 'old_nonexplicit_shared_link';a,b=tu['scope']['tokens'];focus_reasons=[]
        if not any(si==i and a<=ti<b for si,ti in mutual):focus_reasons.append('no_mutual_anchor')
        if any((si==i)!=(a<=ti<b) for si,ti in union):focus_reasons.append('union_crossing')
        if source_masks:focus_reasons.append('inside_larger_source_unit')
        target_masks=h._maskers(tu,units['target'])
        if target_masks:focus_reasons.append('inside_larger_target_unit')
        sr=rolehelper.form_role_evidence(su,sf,pair['source'],rawroles[k['source']],su['scope']['utf16']);tr=rolehelper.form_role_evidence(tu,tf,pair['target'],rawroles[k['target']],envelope);why=set(sf['reasons']+tf['reasons']+st['reasons']+tt['reasons']+focus_reasons)
        if sf['pos']!=tf['pos']:why.add('dictionary_POS_mismatch')
        if sf['number']!=tf['number']:why.add('legacy_number_mismatch')
        if sf['pos']!=pos or tr['role']!=actual:why.add('actual_role_vs_dictionary_POS_mismatch')
        if b-a!=1:why.add('target_not_single_corpus_token')
        pending=[]
        if pos=='verb':pending=['verb_tense_person_aspect_voice_policy_pending']
        elif pos=='adj':pending=['adjective_degree_agreement_policy_pending']
        elif pos=='adv':pending=['adverb_content_degree_negation_scope_policy_pending']
        v={'pair_id':pair['pair_id'],'pair_index':index,'component':pair['source']['component'],'source_endpoint':k['source'],'target_endpoint':k['target'],'source_unit_ref':srref,'target_unit_ref':trref,'source_form_id':sf['form_id'],'target_form_id':tf['form_id'],'source_term_id':st['term_id'],'target_term_id':tt['term_id'],'source_role':sr,'target_role':tr,'source_features':sf['features'],'target_features':tf['features'],'source_raw_analyses':lu['readings'],'target_raw_analyses':rolemap['target'].get(tuple(tu['scope']['utf16']),{}).get('readings',[]),'stratum':stratum,'original_and_legacy_reasons':sorted(why),'policy_pending':pending,'source_masks':source_masks,'target_masks':target_masks,'alignment_ref':{'pair_index':index,'source_token':i,'target_envelope':[ta,tb],'target_aligned_tokens':aligned},'source_name_only_guard':bool(su['guard'] and su['guard']['reason']=='name' and su['guard']['blocked'] and not su['guard']['target_blocked']),'display_approved':False};save_relation(v);classes[(pos,stratum,'all')]+=1
        for whyone in why:reasons[('relation',pos,whyone)]+=1
        if not why:classes[(pos,stratum,'legacy_clear_policy_not_approved')]+=1;phase_occ[(pos,'legacy_clear')].add(occ);focus_alternatives[(pos,occ)].add(tu['scope']['text'])
        phase_occ[(pos,'any_shared_link')].add(occ)
     if not anylink:phase_occ[(pos,'no_shared_link')].add(occ)
     # Direct relations retain all source forms unresolved, no first-form/sense fabrication.
     for tu,tf,trref in target_forms:
      for rel in direct:
       if rel['target_language']!='es' or rel['target_native_entry_id']!=tf['lexeme_id'] or rel['source_pos']!='noun' or h.lookup_key(rel['published_source_spelling'],'en')!=su['key']:continue
       key=(tf['form_id'],tu['unit_id'],rel['relation_id'])
       if key in done_direct:continue
       done_direct.add(key);v={'pair_id':pair['pair_id'],'pair_index':index,'component':pair['source']['component'],'stratum':'new_direct_english_unresolved_candidate','source_endpoint':k['source'],'target_endpoint':k['target'],'source_unit_ref':srref,'target_unit_ref':trref,'target_form_id':tf['form_id'],'candidate_relation_id':rel['relation_id'],'source_forms':[{'form_id':f['form_id'],'pos':f['pos'],'features':f['features'],'number':f['number'],'reasons':f['reasons']} for f in su['forms']],'source_entry_resolved':False,'source_sense_id':None,'source_masks':source_masks,'target_masks':h._maskers(tu,units['target']),'target_original_reasons':tf['reasons'],'target_role':rolehelper.form_role_evidence(tu,tf,pair['target'],rawroles[k['target']],envelope),'alignment_ref':{'pair_index':index,'source_token':i,'target_envelope':[ta,tb],'target_aligned_tokens':aligned},'source_raw_analyses':lu['readings'],'target_raw_analyses':rolemap['target'].get(tuple(tu['scope']['utf16']),{}).get('readings',[]),'display_approved':False};save_relation(v);classes[(pos,v['stratum'],'all')]+=1
    if counts['selected_pairs']%500==0:print(enc({'pairs':counts['selected_pairs'],'relations':counts['relation_rows'],'seconds':time.monotonic()-start}),flush=True)
  assert processed==selected;ordered=sorted(row_sizes);quant={str(q):ordered[min(len(ordered)-1,int(q*(len(ordered)-1)))] for q in [0,.5,.9,.99,1]} if ordered else {};result={'counts':dict(counts),'overlapping_rejection_counts':{str(k):v for k,v in reasons.items()},'relation_classes':{str(k):v for k,v in classes.items()},'source_occurrence_phases_overlapping':{str(k):len(v) for k,v in phase_occ.items()},'feature_combinations':{str(k):v for k,v in features.items()},'legacy_clear_multiple_target_faces_by_POS':dict(collections.Counter(pos for (pos,occ),v in focus_alternatives.items() if len(v)>1)),'prospective_sizes':dict(sizes),'relation_row_UTF8_quantiles':quant,'all_relation_ids_sha256':hashlib.sha256(enc(sorted(relation_ids)).encode()).hexdigest(),'selection_bias':'Pairs selected by earlier1480headcohort; not representative fullcorpus','display_approval':False,'no_new_annotations_or_materialized_proofs':True};b=(json.dumps(result,indent=2)+'\n').encode();assert len(b)<=2*M;(out/'counts.json').write_bytes(b);receipt['complete']=True
 except BaseException as e:receipt['error']=repr(e);raise
 finally:
  receipt.update(seconds=time.monotonic()-start,VmHWM_bytes=int(next(s.split()[1] for s in pathlib.Path('/proc/self/status').read_text().splitlines() if s.startswith('VmHWM:')))*1024,partial_counts=dict(counts),partial_sizes=dict(sizes),outputs={f.name:{'sha256':sha(f),'bytes':f.stat().st_size} for f in out.iterdir() if f.is_file()});(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(enc(receipt),flush=True)
if __name__=='__main__':main()
