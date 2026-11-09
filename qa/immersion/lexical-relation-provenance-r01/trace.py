#!/usr/bin/env python3
"""Bounded keyed read of retained published native relations; no compiler mutation."""
import collections,hashlib,importlib.util,json,os,re,resource,signal,sqlite3,sys,time
from pathlib import Path
Q=Path(__file__).resolve().parent;REPO=Q.parents[2];W=Path('/home/ai/Development/investigations/vipi-lexical-relation-provenance-20261109-r01');INVENTORY=Path('/home/ai/RemoteStorage/dev-workspaces/vipi/20261027-authoring-inventory-003/lexical-inventory-003/inventory.sqlite')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 start=time.monotonic();os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});resource.setrlimit(resource.RLIMIT_AS,(1024**3,)*2)
 def stop(*args):raise TimeoutError('120s keyed read limit')
 signal.signal(signal.SIGALRM,stop);signal.alarm(120);out=W/'trace-r01';out.mkdir(exist_ok=False);receipt={'complete':False,'script_sha256':sha(__file__)};db=None
 try:
  cohort=json.loads((W/'cohort-freeze.json').read_text());assert INVENTORY.stat().st_size==4428693504
  db=sqlite3.connect(INVENTORY.as_uri()+'?mode=ro&immutable=1',uri=True);db.row_factory=sqlite3.Row;db.execute('PRAGMA query_only=ON');db.execute('PRAGMA cache_size=-8192');db.set_progress_handler(lambda:int(time.monotonic()-start>115),1000)
  sys.path.insert(0,str(REPO/'language-packs'));spec=importlib.util.spec_from_file_location('frozen_gloss_linker',REPO/'language-packs/build_native_gloss_links.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);raw={}
  def entry(identifier):
   if str(identifier) not in raw:
    e=db.execute('SELECT * FROM native_entries WHERE source_line=?',(identifier,)).fetchone();assert e is not None,identifier
    raw[str(identifier)]={'entry':dict(e),'senses':[dict(x) for x in db.execute('SELECT * FROM native_senses WHERE source_line=? ORDER BY sense_index',(identifier,))],'forms':[dict(x) for x in db.execute('SELECT * FROM native_forms WHERE source_line=? ORDER BY form,tags',(identifier,))]}
   return raw[str(identifier)]
  def english(word,pos):
   choices=[];accepted=[]
   for row in db.execute("SELECT source_line,tags FROM native_entries WHERE language='en' AND normalized=? AND headword=? AND part_of_speech=? ORDER BY source_line",(word,word,pos)):
    e=entry(row['source_line']);excluded=bool(set(json.loads(row['tags']))&module.EXCLUDED);leaf=False;alias=False
    for sense in e['senses']:
     if set(json.loads(sense['tags']))&module.EXCLUDED:continue
     if json.loads(sense['form_of']) or json.loads(sense['alt_of']):alias=True
     elif json.loads(sense['glosses']):leaf=True
    ok=not excluded and leaf and not alias
    if ok:accepted.append(row['source_line'])
    choices.append({'source_line':row['source_line'],'excluded_entry':excluded,'has_leaf':leaf,'has_alias':alias,'accepted_before_uniqueness':ok})
   return {'word':word,'pos':pos,'all_entries':choices,'accepted_entry_ids':accepted,'compiler_selected_id':accepted[0] if len(accepted)==1 else None,'reason':'unique_leaf_entry' if len(accepted)==1 else 'no_leaf_nonalias_entry' if not accepted else 'multiple_leaf_entries'}
  identifiers={x['form']['lexeme_id'] for x in cohort['forms']}|{15814};extra=[dict(x) for x in db.execute("SELECT * FROM native_entries WHERE language='es' AND normalized='otoño' AND part_of_speech='noun' ORDER BY source_line")];identifiers.update(x['source_line'] for x in extra)
  for identifier in sorted(identifiers):entry(identifier)
  traces=[];alias_edges=[]
  for identifier in sorted(identifiers):
   data=entry(identifier);e=data['entry'];senses=data['senses'];rows=[(s['glosses'],s['tags'],s['form_of'],s['alt_of']) for s in senses];actual=module.counterparts(rows);reasons=[];leaves=set()
   if set(json.loads(e['tags']))&module.EXCLUDED:reasons.append('excluded_entry_tags')
   for sense in senses:
    tags=set(json.loads(sense['tags']))
    if tags&module.EXCLUDED:continue
    if tags-module.GRAMMATICAL_TAGS:reasons.append('non_grammatical_sense_tags')
    if json.loads(sense['form_of']) or json.loads(sense['alt_of']):reasons.append('published_form_or_alias_relation')
    glosses=json.loads(sense['glosses'])
    if not glosses:reasons.append('missing_gloss')
    else:leaves.add(glosses[-1])
    for relation in ['form_of','alt_of']:
     for link in json.loads(sense[relation]):
      word=link.get('word') if isinstance(link,dict) else None
      if word:
       targets=[dict(x) for x in db.execute('SELECT * FROM native_entries WHERE language=? AND normalized=? AND headword=? AND part_of_speech=? ORDER BY source_line',(e['language'],word.lower(),word,e['part_of_speech']))]
       for target in targets:entry(target['source_line'])
       alias_edges.append({'source_line':identifier,'sense_index':sense['sense_index'],'relation':relation,'published_link':link,'exact_same_POS_target_entry_ids':[t['source_line'] for t in targets],'unique_identity_claim':False})
   if len(leaves)!=1:reasons.append('not_exactly_one_distinct_leaf')
   elif actual is None and not reasons:reasons.append('leaf_outside_bare_gloss_grammar')
   trace={'source_line':identifier,'language':e['language'],'headword':e['headword'],'pos':e['part_of_speech'],'counterparts_result':actual,'counterparts_reasons_overlap':sorted(set(reasons)),'english_resolutions':[]}
   if actual and e['language']!='en':trace['english_resolutions']=[english(word,e['part_of_speech']) for word in actual[1]]
   if e['language']=='en':trace['english_self_resolution']=english(e['headword'].lower(),e['part_of_speech'])
   traces.append(trace)
  # A relation is recorded only if explicitly published; exact spelling does not assert synonymy.
  result={'production':False,'inventory_route':str(INVENTORY),'expected_historical_inventory_sha256':'8c97e9de2ce8e94ce9754475a85eb27cd956ee0ba69491fe270376e3177ceb17','fresh_whole_inventory_hash_verified':False,'identity_basis':'Established retained readonly route, exact size, embedded metadata and published prior archive binding; no bulk hash/copy.','inventory_metadata':dict(db.execute('SELECT key,value FROM metadata')),'cohort_sha256':sha(W/'cohort-freeze.json'),'gloss_compiler_sha256':sha(REPO/'language-packs/build_native_gloss_links.py'),'extra_otono_entries':extra,'raw_entries':raw,'selected_entry_hashes':{k:hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest() for k,v in raw.items()},'compiler_traces':traces,'published_alias_edges':alias_edges,'query_contract':'Exact SELECT statements retained in hash-bound trace.py: source_line PK, language/normalized index, source_line-keyed senses/forms; no full scan/new index.','limits':'Compiler trace is read-only; no build or new relation emitted. Native gloss/alias publication is evidence, not occurrence-role or contextual meaning approval.'}
  blob=(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode();assert len(blob)<8*1024**2
  with (out/'evidence.json').open('xb') as f:f.write(blob)
  receipt.update(complete=True,entries=len(raw),cohort_native_ids=len(identifiers),alias_edges=len(alias_edges),output_sha256=sha(out/'evidence.json'),output_bytes=len(blob))
 except BaseException as e:receipt['error']=repr(e);raise
 finally:
  if db:db.close()
  receipt.update(seconds=time.monotonic()-start,memory={k:int(v.split()[0])*1024 for k,v in (s.split(':',1) for s in Path('/proc/self/status').read_text().splitlines() if s.startswith(('VmHWM:','VmPeak:')))},output_exists=(out/'evidence.json').exists())
  with (out/'receipt.json').open('x') as f:json.dump(receipt,f,indent=2);f.write('\n')
  print(json.dumps(receipt),flush=True)
if __name__=='__main__':main()
