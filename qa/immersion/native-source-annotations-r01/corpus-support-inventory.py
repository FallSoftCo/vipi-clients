#!/usr/bin/env python3
"""Bounded, read-only inventory; no lexical acceptance or runtime activation."""
import collections, functools, gzip, hashlib, json, os, pathlib, re, resource, shutil, signal, sqlite3, time
HERE=pathlib.Path(__file__).resolve().parent
W=pathlib.Path('/home/ai/Development/investigations/vipi-immersion-reconciliation-20261107-r01/corpus-phrase-extraction-r01')
OUT=pathlib.Path('/home/ai/Development/investigations/vipi-corpus-support-inventory-20261108-r01')
START=time.monotonic()
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def failtime(*a):raise TimeoutError('180 second elapsed limit')
def main():
 os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
 resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,256*1024**2))
 signal.signal(signal.SIGALRM,failtime);signal.alarm(180)
 assert shutil.disk_usage(W).free>=8*1024**3+32*1024**2
 OUT.mkdir(exist_ok=False)
 paths={'candidates':W/'phrases/candidates.sqlite','dictionary':W/'phrases/dictionary-units.sqlite','inputs':HERE/'inputs.json'}
 hashes={k:sha(p) for k,p in paths.items()}
 assert hashes['candidates']=='54cbd4e1bc1af66b5045fb5e683b2e6e5abbd333421dd272357e061a32772747'
 assert hashes['dictionary']=='8a382e08cab53e7a26095d849192508df1cff3b4ab0a55dd494fef459d414f57'
 assert hashes['inputs']=='cb37306db9723bf39ea41204674515c890fa12186d7e6ac052db06e6d1f27b14'
 db=sqlite3.connect(paths['candidates'].as_uri()+'?mode=ro&immutable=1',uri=True);db.row_factory=sqlite3.Row
 dd=sqlite3.connect(paths['dictionary'].as_uri()+'?mode=ro&immutable=1',uri=True)
 db.execute('PRAGMA cache_size=-8192');dd.execute('PRAGMA cache_size=-8192')
 @functools.lru_cache(maxsize=32)
 def units(lang,key):
  row=dd.execute('SELECT evidence FROM units WHERE language=? AND key=?',(lang,key)).fetchone()
  return json.loads(row[0]) if row else []
 groups={};variants={};special=[]
 for vid,sids in dd.execute("SELECT variant,shared_sense_ids FROM corroboration WHERE status='shared_complete_dictionary_sense'"):
  r=dict(db.execute('SELECT * FROM variants WHERE id=?',(vid,)).fetchone())
  key=(r['pair'],r['arm'],r['source_key']);sidset=set(json.loads(sids));tl=r['pair'].split('-')[1]
  src=units('en',r['source_key']);tgt=units(tl,r['target_key'])
  # Explicit source-linked sense IDs are distinguished from generated native glosses.
  source_terms={(u['pos'],t['sense_id']):(t['label'],bool(t['explicit']),bool(t['eligible'])) for u in src for t in u['terms']}
  target_terms={(u['pos'],t['sense_id'],u['lexeme_id']):bool(t['eligible']) for u in tgt for t in u['terms']}
  supported={(pos,sid) for pos,sid in source_terms if sid in sidset and source_terms[pos,sid][1] and source_terms[pos,sid][2] and any(tp==pos and ts==sid and ok for (tp,ts,lex),ok in target_terms.items())}
  g=groups.setdefault(key,{'pair':key[0],'arm':key[1],'source_key':key[2],'source_tokens':r['source_tokens'],'variants':0,'target_spellings':set(),'target_lexemes':set(),'explicit_source_senses':set(),'supported_same_pos_senses':set(),'components':set(),'observations_sum':0,'aligned_occurrences':0})
  g['variants']+=1;g['target_spellings'].add(r['target_key']);g['observations_sum']+=r['observations']
  g['explicit_source_senses'].update((p,s) for (p,s),(lab,ex,el) in source_terms.items() if ex and el)
  g['supported_same_pos_senses'].update(supported)
  g['target_lexemes'].update((p,s,lex) for (p,s,lex),ok in target_terms.items() if ok and (p,s) in supported)
  g['components'].update(x[0] for x in db.execute('SELECT component FROM components WHERE variant=?',(vid,)))
  variants[vid]=key
  if r['source_key'] in {'play','too','visit','flash','fruits','tech','book','water'}:
   special.append({'pair':key[0],'arm':key[1],'source_key':key[2],'target':r['target_key'],'variant':vid,'observations':r['observations'],'same_pos_explicit_senses':[{'pos':p,'sense_id':s,'label':source_terms[p,s][0]} for p,s in sorted(supported)],'all_shared_ids':sorted(sidset),'example_pair_index':r['example_pair_index'],'source_tokens':[r['source_start'],r['source_end']]})
 # Logs are in paired-record order. Deduplicate alternative boundaries within each
 # record, retaining each arm and source span. This is not statistical independence.
 for pair in ['en-sw','en-es']:
  p=W/'phrases'/f'{pair}-observations.jsonl.gz';hashes[p.name]=sha(p)
  previous=None;seen=set()
  with gzip.open(p,'rt') as f:
   for line in f:
    o=json.loads(line);idx=o['pair_index']
    if previous is not None and idx!=previous:
     for key,span in seen:groups[key]['aligned_occurrences']+=1
     seen.clear()
    previous=idx
    if o['variant_id'] in variants:seen.add((variants[o['variant_id']],tuple(o['source_tokens'])))
   for key,span in seen:groups[key]['aligned_occurrences']+=1
 summary=collections.defaultdict(collections.Counter);rows=[]
 for key,g in sorted(groups.items()):
  c=summary[(key[0],key[1],'word' if g['source_tokens']==1 else 'phrase')];c['source_keys']+=1;c['variants']+=g['variants'];c['aligned_source_occurrences']+=g['aligned_occurrences']
  for field in ['explicit_source_senses','supported_same_pos_senses']:
   by=collections.defaultdict(set)
   for pos,sid in g[field]:by[pos].add(sid)
   c[field+':any_same_pos_multiple']+=any(len(s)>1 for s in by.values())
   c[field+':singleton_total']+=sum(map(len,by.values()))==1
   c[field+':zero']+=not by
  c['alternate_target_spellings']+=len(g['target_spellings'])>1;c['alternate_supported_target_identities']+=len(g['target_lexemes'])>1
  c['one_component']+=len(g['components'])==1;c['multiple_components']+=len(g['components'])>1
  row={k:(sorted(v) if isinstance(v,set) and k!='components' else len(v) if k=='components' else v) for k,v in g.items()};rows.append(row)
 probes=[]
 for case in json.loads(paths['inputs'].read_text())['cases']:
  # Diagnostic spelling availability, not native matcher geometry or sense fit.
  text=case['text'].casefold();matches=[]
  for g in rows:
   if re.search(r'(?<!\w)'+re.escape(g['source_key'])+r'(?!\w)',text):
    matches.append({'pair':g['pair'],'arm':g['arm'],'key':g['source_key'],'variants':g['variants'],'supported_same_pos_senses':len(g['supported_same_pos_senses']),'target_spellings':g['target_spellings']})
  probes.append({'id':case['id'],'text':case['text'],'matches':matches})
 examples=collections.defaultdict(list)
 for s in special:examples[s['pair']].append(s['example_pair_index'])
 pairs=[]
 for pair,inds in examples.items():
  wanted=set(inds);p=W/f'{pair}-pairs.jsonl.gz';hashes[p.name]=sha(p)
  with gzip.open(p,'rt') as f:
   for line in f:
    r=json.loads(line)
    if r['index'] in wanted:pairs.append(r)
 result={'production':False,'semantic_approval':False,'input_hashes':hashes,'summary':[dict(pair=k[0],arm=k[1],unit=k[2],**v) for k,v in sorted(summary.items())],'groups':rows,'confusables':special,'probe_availability':probes,'retained_example_pairs':pairs,'limits':['Source sense IDs are dictionary identities, not exhaustive real senses or contextual truth. Native-gloss IDs are excluded from explicit supported counts.','Aligned source occurrence means distinct paired record index/source span per arm and key; duplicates across records may remain. Component counts provide a second dependence measure; neither is statistically independent evidence.','Spelling variants and target lexeme/sense/POS identities are reported separately; multiple target identities may still express one sense.','Probe matching is casefolded boundary spelling availability, not native geometry or semantic approval. No target patches or defaults changed.']}
 payload=json.dumps(result,ensure_ascii=False,indent=2)+'\n';assert len(payload.encode())<31*1024**2
 (OUT/'inventory.json').write_text(payload)
 return {'complete':True,'production':False,'input_hashes':hashes,'output':str(OUT/'inventory.json'),'output_sha256':sha(OUT/'inventory.json'),'output_bytes':len(payload.encode()),'summary':result['summary'],'groups':len(rows),'variants':len(variants)}
if __name__=='__main__':
 try:receipt=main()
 except BaseException as e:receipt={'complete':False,'error':repr(e),'production':False}
 receipt.update(seconds=time.monotonic()-START,max_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,code_sha256=sha(pathlib.Path(__file__)))
 (HERE/'corpus-support-inventory-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
 print(json.dumps(receipt))
