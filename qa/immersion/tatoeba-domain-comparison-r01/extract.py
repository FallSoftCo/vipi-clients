#!/usr/bin/env python3
"""Reviewed, stage-separated Tatoeba extraction. No automatic stage chaining."""
import argparse,collections,gzip,hashlib,heapq,json,os,resource,shutil,signal,socket,sqlite3,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from prepare_statistical_alignment_pilot import tokenize
from build_corpus_exclusions import fingerprint
from conversation_corpus import key

SCHEMA={'sentences':['id','language','text','owner','added','modified','normalized','component','partition'],'links':['a','b'],'tags':['sentence','tag','owner','added'],'tag_metadata':['id','name'],'metadata':['key','value']}
BAD="name LIKE '@%' OR lower(name) LIKE '%unnatural%' OR lower(name) LIKE '%incorrect%' OR lower(name) IN ('not natural','non natural','less than natural')"
def reviewed_blocked_ids(names, raw_ids, review):
 # Exact metadata-only exceptions frozen before any sentence selection.
 for item in review['retained_non_text_flags']:
  assert names[item['id']]==item['name'] and item['id'] in raw_ids
 return raw_ids-{item['id'] for item in review['retained_non_text_flags']}
# Only metadata columns are selected here, never normalized/raw sentence text.
SQL="""SELECT l.a,l.b,s.language,t.language,s.owner,t.owner,s.component,t.component
FROM links l JOIN sentences s ON s.id=l.a JOIN sentences t ON t.id=l.b
WHERE s.partition='development' AND t.partition='development'
AND ((s.language='en' AND t.language='es') OR (s.language='es' AND t.language='en'))"""
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def enc(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def write(p,x):
 with p.open('x') as f:f.write(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def vm():return {k:int(v.split()[0])*1024 for k,v in (s.split(':',1) for s in Path('/proc/self/status').read_text().splitlines() if s.startswith(('VmHWM:','VmPeak:','VmRSS:')))}
def main():
 p=argparse.ArgumentParser();p.add_argument('stage',choices=['inspect','select','fetch']);p.add_argument('--source',type=Path,required=True);p.add_argument('--work',type=Path,required=True);p.add_argument('--inputs',type=Path,required=True);p.add_argument('--reviewed-inspection-sha256');p.add_argument('--reviewed-selection-sha256');a=p.parse_args()
 protocol=json.loads((HERE/'protocol.json').read_text());limits=protocol['extraction_bounds'];start=time.monotonic()
 # Fail before any source hash/open on an unintended host, mount or directory.
 assert socket.gethostname()=='fallsoft-production-20261106','production host required'
 root=Path('/srv/fallsoft/staging/vipi-tatoeba-domain-comparison-20261108-r01')
 assert root.resolve()==root,'staging root must not redirect elsewhere'
 for supplied,expected in [(a.source,root/'source/corpus.sqlite'),(a.work,root/'outputs'),(a.inputs,root/'inputs')]:
  assert supplied.is_absolute() and supplied.resolve()==expected,str(supplied)
 os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});os.nice(10);resource.setrlimit(resource.RLIMIT_AS,(limits['address_space_bytes'],)*2)
 def timed_out(*args):raise TimeoutError('bounded extraction stage deadline')
 signal.signal(signal.SIGALRM,timed_out);signal.alarm(limits['seconds_per_stage'])
 assert shutil.disk_usage(a.work.parent).free>=limits['minimum_free_bytes']+limits['maximum_output_bytes']
 a.work.mkdir(exist_ok=True)
 def guard():
  assert time.monotonic()-start<limits['seconds_per_stage']
  assert shutil.disk_usage(a.work).free>=limits['minimum_free_bytes']
  assert sum(x.stat().st_size for x in a.work.rglob('*') if x.is_file())<limits['maximum_output_bytes']-65536
 out=a.work/a.stage;out.mkdir(exist_ok=False)
 receipt={'stage':a.stage,'complete':False,'production':False,'source':str(a.source),'builder_sha256':sha(Path(__file__)),'protocol_sha256':sha(HERE/'protocol.json')}
 db=None
 try:
  assert a.source.stat().st_size==protocol['source']['bytes'] and sha(a.source)==protocol['source']['sha256']
  assert sha(a.inputs/'input-freeze.json')==protocol['input_freeze']['sha256']
  frozen=json.loads((a.inputs/'input-freeze.json').read_text())
  assert sha(a.inputs/'exclusions.json')==frozen['exclusions']['sha256']
  for k in ['tokenizer','fingerprint','normalization']:
   assert sha(HERE.parent/Path(frozen[k]['path']).name)==frozen[k]['sha256']
  write(out/'execution-freeze.json',receipt|{'before_outputs':True,'input_freeze_sha256':protocol['input_freeze']['sha256'],'source_sha256':protocol['source']['sha256'],'bounds':limits})
  db=sqlite3.connect(a.source.resolve().as_uri()+'?mode=ro&immutable=1',uri=True);db.execute('PRAGMA query_only=ON');db.execute('PRAGMA cache_size=-32768');db.execute('PRAGMA temp_store=FILE');db.set_progress_handler(lambda:int(time.monotonic()-start>limits['seconds_per_stage']),10000)
  for table,cols in SCHEMA.items():assert [r[1] for r in db.execute('PRAGMA table_info('+table+')')]==cols,table
  meta=json.loads(db.execute("SELECT value FROM metadata WHERE key='receipt'").fetchone()[0]);assert meta['tags_schema']=='tag_id,sentence_id,username,added_time';assert meta['split_recipe']==protocol['source']['split_recipe']
  names={i:name for i,name in db.execute('SELECT id,name FROM tag_metadata')};bad={r[0] for r in db.execute('SELECT id FROM tag_metadata WHERE '+BAD)}
  if a.stage=='inspect':
   # No counts requiring sentence text; query is explained, not executed.
   indexes=list(db.execute("SELECT name,tbl_name,sql FROM sqlite_master WHERE type='index'"))
   assert any(r[0]=='tags_sentence' for r in indexes)
   write(out/'metadata.json',{'schema':SCHEMA,'metadata_receipt':meta,'tag_names':names,'blocked_tag_ids':sorted(bad),'blocked_tag_name_count':len(bad),'indexes':indexes,'selection_query_plan':list(db.execute('EXPLAIN QUERY PLAN '+SQL)),'sentence_text_read':False,'quality_limit':'No tag, owner or absence of a flag certifies translation quality.'})
  else:
   inspection=a.work/'inspect/metadata.json';assert a.reviewed_inspection_sha256 and sha(inspection)==a.reviewed_inspection_sha256
   observed=json.loads(inspection.read_text());assert observed['blocked_tag_ids']==sorted(bad)
   review=protocol['selection']['metadata_review']
   assert a.reviewed_inspection_sha256==review['inspection_sha256']
   bad=reviewed_blocked_ids(names,bad,review)
   def tags(i):
    result=[{'sentence':sid,'tag':tag,'name':names[tag],'owner':owner,'added':added} for sid,tag,owner,added in db.execute('SELECT sentence,tag,owner,added FROM tags WHERE sentence=? ORDER BY tag,owner,added',(i,))]
    return result
   if a.stage=='select':
    heap=[];counts=collections.Counter();cap=protocol['selection']['metadata_cap']
    for row in db.execute(SQL):
     left,right,sl,tl,so,to,sc,tc=row;counts['development_direct_rows']+=1
     assert left<right and sc==tc and sc is not None
     st,tt=tags(left),tags(right)
     if any(t['tag'] in bad for t in st+tt):counts['blocked_tag_pairs']+=1;continue
     rank=hashlib.sha256((protocol['selection']['seed']+'|'+str(left)+'|'+str(right)).encode()).hexdigest()
     item=(-int(rank,16),rank,row,st,tt)
     if len(heap)<cap:heapq.heappush(heap,item)
     elif item[0]>heap[0][0]:heapq.heapreplace(heap,item)
     if counts['development_direct_rows']%1000==0:guard()
    path=out/'candidates.jsonl.gz'
    with gzip.open(path,'xt') as f:
     for _,rank,row,st,tt in sorted(heap,key=lambda r:r[1]):f.write(enc({'rank':rank,'canonical_metadata':row,'a_tags':st,'b_tags':tt})+'\n')
    write(out/'selection-freeze.json',{'complete':True,'before_sentence_fetch':True,'protocol_sha256':receipt['protocol_sha256'],'inspection_sha256':sha(inspection),'candidate_sha256':sha(path),'candidate_count':len(heap),'counts':dict(counts),'ranking':'SHA256(seed|canonical_a|canonical_b), no sentence text or target quality'})
   else:
    selected=a.work/'select/selection-freeze.json';assert a.reviewed_selection_sha256 and sha(selected)==a.reviewed_selection_sha256
    selection=json.loads(selected.read_text());assert selection['protocol_sha256']==receipt['protocol_sha256'] and selection['inspection_sha256']==sha(inspection)
    candidates=a.work/'select/candidates.jsonl.gz';assert sha(candidates)==selection['candidate_sha256']
    excluded=set(json.loads((a.inputs/'exclusions.json').read_text())['hashes']);seen=set();counts=collections.Counter();accepted=0;components=collections.Counter();owners=collections.Counter();lengths={'en':collections.Counter(),'es':collections.Counter()}
    def endpoint(i,expected):
     # SQL excludes reserved before its text can be returned.
     row=db.execute("SELECT id,language,text,owner,added,modified,normalized,component,partition FROM sentences WHERE id=? AND partition='development'",(i,)).fetchone();assert row is not None
     sid,lang,text,owner,added,modified,normalized,component,partition=row
     assert (lang,owner,component)==expected and normalized==key(text)
     tok=tokenize(text) if '|||' not in text else []
     # Reject oversized/delimited sentences before quadratic UTF16-prefix work.
     if not 2<=len(tok)<=60:tok=[]
     return {'id':sid,'language':lang,'text':text,'owner':owner,'added':added,'modified':modified,'fingerprint':fingerprint(lang,text).hex(),'component':component,'partition':partition,'url':'https://tatoeba.org/en/sentences/show/'+str(sid),'record_sha256':hashlib.sha256(enc(row).encode()).hexdigest(),'tokens':[{'text':t,'codepoints':[s,e],'utf16':[len(text[:s].encode('utf-16-le'))//2,len(text[:e].encode('utf-16-le'))//2]} for t,s,e in tok]}
    with gzip.open(candidates,'rt') as src,gzip.open(out/'en-es-pairs.jsonl.gz','xt') as pairs,(out/'en-es.txt').open('x') as lines,gzip.open(out/'decisions.jsonl.gz','xt') as decisions:
     for line in src:
      c=json.loads(line);left,right,sl,tl,so,to,sc,tc=c['canonical_metadata'];reason=None
      if accepted>=protocol['selection']['accepted_cap']:
       decisions.write(enc({'rank':c['rank'],'a':left,'b':right,'reason':'accepted_cap_no_text_fetch'})+'\n');counts['accepted_cap_no_text_fetch']+=1;continue
      assert tags(left)==c['a_tags'] and tags(right)==c['b_tags']
      l,r=endpoint(left,(sl,so,sc)),endpoint(right,(tl,to,tc));l['tags']=c['a_tags'];r['tags']=c['b_tags']
      if l['language']!='en':l,r=r,l
      assert (l['language'],r['language'])==('en','es')
      if l['fingerprint'] in excluded or r['fingerprint'] in excluded:reason='exposed_full_text'
      elif any(not 2<=len(e['tokens'])<=60 or '|||' in e['text'] for e in [l,r]):reason='token_length_or_delimiter'
      pair_id=hashlib.sha256((l['fingerprint']+r['fingerprint']).encode()).hexdigest()
      if reason is None and pair_id in seen:reason='duplicate_normalized_direct_pair'
      decisions.write(enc({'rank':c['rank'],'a':left,'b':right,'source_fingerprint':l['fingerprint'],'target_fingerprint':r['fingerprint'],'pair_id':pair_id,'reason':reason or 'accepted'})+'\n');counts[reason or 'accepted']+=1
      if reason:continue
      seen.add(pair_id)
      record={'index':accepted,'pair_id':pair_id,'pair':'en-es','source':l,'target':r,'provenance':{'source_namespace':'Tatoeba','source_license':protocol['source']['license'],'distribution_status':'research_only_not_approved_pack','direct_edge':[left,right],'source_database_sha256':protocol['source']['sha256'],'hash_selection_rank':c['rank']}}
      pairs.write(enc(record)+'\n');lines.write(' '.join(t['text'].casefold() for t in l['tokens'])+' ||| '+' '.join(t['text'].casefold() for t in r['tokens'])+'\n');accepted+=1;components[l['component']]+=1
      for e in [l,r]:owners[e['language']+'|'+e['owner']]+=1;lengths[e['language']][len(e['tokens'])]+=1
      if accepted%250==0:guard()
    receipt.update(accepted_pairs=accepted,counts=dict(counts),distinct_components=len(components),largest_component_pairs=max(components.values(),default=0),distinct_endpoint_owners=len(owners),token_length_histograms={k:dict(v) for k,v in lengths.items()},matched40k=accepted==40000)
    if accepted!=40000:raise RuntimeError('Frozen pool shortage; retain partial output, no automatic widening/backfill')
  guard();receipt['complete']=True
 except BaseException as exc:receipt['error']=repr(exc);raise
 finally:
  if db:db.close()
  receipt.update(seconds=time.monotonic()-start,measurement=vm(),free_bytes=shutil.disk_usage(a.work).free,outputs={p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in out.iterdir() if p.is_file()})
  write(out/'receipt.json',receipt);print(enc(receipt),flush=True)
if __name__=='__main__':main()
