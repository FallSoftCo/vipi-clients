"""Read-only retained-data breadth census, not a selector or annotation run."""
import collections,gzip,hashlib,json,os,pathlib,re,resource,shutil,signal,socket,time,unicodedata,sqlite3
R=pathlib.Path('/srv/fallsoft/staging/vipi-coverage-expansion-inventory-20261109-r01');M=1024**2
sha=lambda p:hashlib.file_digest(open(p,'rb'),'sha256').hexdigest()
def norm(t):return ' '.join(unicodedata.normalize('NFC',t).casefold().split())
def db(p):
 d=sqlite3.connect(pathlib.Path(p).as_uri()+'?mode=ro&immutable=1',uri=True);d.execute('PRAGMA query_only=ON');d.execute('PRAGMA cache_size=-8192');d.execute('PRAGMA temp_store=MEMORY');return d

def main():
 assert socket.gethostname()=='fallsoft-production-20261106';start=time.monotonic();os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});os.nice(10);resource.setrlimit(resource.RLIMIT_AS,(1024**3,)*2);signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('120s')));signal.alarm(120);p=json.loads((R/'protocol.json').read_text());assert sha(__file__)==p['code_sha256'];out=R/'outputs';out.mkdir(exist_ok=False);r={'complete':False,'protocol_sha256':sha(R/'protocol.json'),'free_bytes':shutil.disk_usage(R).free};assert r['free_bytes']>8*1024**3+32*M
 try:
  r['input_hashes']={k:sha(v['path']) for k,v in p['inputs'].items()};assert all(r['input_hashes'][k]==v['sha256'] for k,v in p['inputs'].items())
  inventory=json.loads(pathlib.Path(p['inputs']['endpoint_inventory']['path']).read_text());endpoint_by_id={(v['language'],v['endpoint_id']):k for k,v in inventory['endpoints'].items()};geometry={};corpora={}
  for name in ['tatoeba_en_es','pgv_en_es','pgv_en_sw']:
   count=0;ids=set();sources=set();targets=set();texts={'source':set(),'target':set()};components=collections.Counter();tokens=collections.Counter();langs=collections.Counter();partitions=collections.Counter()
   with gzip.open(p['inputs'][name]['path'],'rt') as f:
    for line in f:
     x=json.loads(line);count+=1;ids.add(x['pair_id']);s=x['source'];t=x['target'];assert s['component']==t['component'];components[s['component']]+=1;sources.add(s['id']);targets.add(t['id'])
     for side,e in [('source',s),('target',t)]:
      lang=e.get('language',e.get('lang'));langs[lang]+=1;partitions[e['partition']]+=1;texts[side].add(hashlib.sha256(norm(e['text']).encode()).hexdigest());tokens[side]+=len(e['tokens'])
      if name=='tatoeba_en_es' and (lang,e['id']) in endpoint_by_id:geometry[endpoint_by_id[(lang,e['id'])]]={tuple(z['utf16']) for z in e['tokens']}
   corpora[name]={'pairs':count,'unique_pair_ids':len(ids),'source_ids':len(sources),'target_ids':len(targets),'source_normalized_texts':len(texts['source']),'target_normalized_texts':len(texts['target']),'components':len(components),'largest_component_pairs':max(components.values()),'tokens':dict(tokens),'endpoint_languages':dict(langs),'endpoint_partitions':dict(partitions),'component_independence_not_guaranteed':True}
  dictionaries={};term_maps={};posscope={'noun','verb','adj','adv'}
  for lang in ['en','es','sw']:
   d=db(p['inputs']['dictionary_'+lang]['path']);lex={row[0]:row[1] for row in d.execute('select id,pos from lexemes')};allterms=collections.Counter();eligible=collections.Counter();explicit=collections.Counter();strata=collections.Counter();maps=collections.defaultdict(lambda:collections.defaultdict(set));withterms=set();expwith=set();nonexpwith=set()
   for lid,sid,flag,ex in d.execute('select t.lexeme,t.sense,t.eligible,s.explicit from terms t join senses s on s.id=t.sense'):
    pos=lex[lid];allterms[pos]+=1;withterms.add(lid);strata[(pos,flag,ex)]+=1
    if flag:
     eligible[pos]+=1;maps['eligible_any'][(sid,pos)].add(lid)
     if ex:explicit[pos]+=1;expwith.add(lid);maps['eligible_explicit'][(sid,pos)].add(lid)
     else:nonexpwith.add(lid);maps['eligible_nonexplicit'][(sid,pos)].add(lid)
   dictionaries[lang]={'bytes':pathlib.Path(p['inputs']['dictionary_'+lang]['path']).stat().st_size,'lexemes_by_POS':dict(collections.Counter(lex.values())),'zero_terms_by_POS':dict(collections.Counter(pos for lid,pos in lex.items() if lid not in withterms)),'without_eligible_explicit_term_by_POS':dict(collections.Counter(pos for lid,pos in lex.items() if lid not in expwith)),'with_eligible_nonexplicit_term_by_POS':dict(collections.Counter(lex[lid] for lid in nonexpwith)),'term_rows_by_POS_eligible_explicit':{str(k):v for k,v in strata.items()},'surface_rows_by_POS':dict(d.execute('select l.pos,count(*) from surfaces f join lexemes l on f.lexeme=l.id group by l.pos')),'guard_reason_rows':dict(d.execute('select reason,count(*) from guards group by reason')),'native_sense_counts_by_POS':dict(d.execute('select pos,sum(senses) from lexemes group by pos'))};term_maps[lang]=maps;d.close()
  linked={}
  for src,tgt in [('en','es'),('es','en'),('en','sw'),('sw','en')]:
   linked[src+'-'+tgt]={}
   for stratum in ['eligible_any','eligible_explicit','eligible_nonexplicit']:
    targets=collections.defaultdict(set);poss={}
    for key,ls in term_maps[src][stratum].items():
     if key[1] not in posscope:continue
     ts=term_maps[tgt][stratum].get(key,set())
     if not ts:continue
     for lid in ls:targets[lid].update(ts);poss[lid]=key[1]
    linked[src+'-'+tgt][stratum]={pos:{'source_lexemes_with_target':sum(poss[l]==pos for l in targets),'source_lexemes_multiple_target_lexemes':sum(poss[l]==pos and len(v)>1 for l,v in targets.items()),'distinct_target_lexemes':len(set().union(*(v for l,v in targets.items() if poss[l]==pos)))} for pos in sorted(posscope)}
  roles=collections.defaultdict(collections.Counter);role_endpoints=collections.defaultdict(lambda:collections.defaultdict(set));d=db(p['inputs']['evidence']['path']);tagmap=json.loads(pathlib.Path(p['inputs']['apertium_protocol']['path']).read_text())['tag_to_UPOS'];seen=set()
  for raw, in d.execute("select data from objects where kind='lexical_unit'"):
   u=json.loads(raw);k=u['endpoint_key'];span=tuple(u['utf16']);ident=(k,span);assert ident not in seen;seen.add(ident);lang=inventory['endpoints'][k]['language'];read=u['contextual_readings'];reason='ambiguous' if len(read)!=1 else 'unknown' if read[0].startswith('*') else 'not_exact_native_token' if span not in geometry[k] else 'multi_analysis' if '+' in read[0] or '#' in read[0] else None
   tags=re.findall(r'<([^>]+)>',read[0]) if len(read)==1 else [];role=reason or tagmap.get(tags[0] if tags else '', 'unmapped');roles[lang][role]+=1;role_endpoints[lang][role].add(k)
  d.close();result={'corpora':corpora,'packed_dictionaries':dictionaries,'shared_term_flag_links':linked,'link_count_limit':'Flags/POS/shared identity only; no complete-form, qualifier-reason, source/target guard, alignment, current occurrence role or meaning approval. Native sense counts and linked terms are different units; do not subtract as missing senses.','existing_role_units':{lang:{'unit_counts':dict(v),'distinct_endpoint_counts_overlapping':{role:len(ids) for role,ids in role_endpoints[lang].items()}} for lang,v in roles.items()},'annotated_endpoints':len(geometry),'annotation_cohort_pairs':inventory['distinct_pairs'],'role_scope_limit':'Existing selected7115pairs; no new annotation. Exact native single-token spans; counts acrossroles/endpoints overlap.','no_training_annotation_selector_or_activation':True};b=(json.dumps(result,indent=2)+'\n').encode();assert len(b)<2*M;(out/'inventory.json').write_bytes(b);r['complete']=True
 except BaseException as e:r['error']=repr(e);raise
 finally:
  r.update(seconds=time.monotonic()-start,VmHWM_bytes=int(next(s.split()[1] for s in pathlib.Path('/proc/self/status').read_text().splitlines() if s.startswith('VmHWM:')))*1024,outputs={f.name:{'bytes':f.stat().st_size,'sha256':sha(f)} for f in out.iterdir() if f.is_file()});(out/'receipt.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r),flush=True)
if __name__=='__main__':main()
