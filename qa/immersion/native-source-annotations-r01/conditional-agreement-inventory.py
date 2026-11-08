#!/usr/bin/env python3
import collections,hashlib,json,os,pathlib,resource,shutil,signal,sqlite3,time,unicodedata
HERE=pathlib.Path(__file__).resolve().parent
BASE=pathlib.Path('/home/ai/Development/investigations')
W=BASE/'vipi-immersion-reconciliation-20261107-r01/corpus-phrase-extraction-r01'
OUT=BASE/'vipi-conditional-agreement-inventory-20261108-r01'
START=time.monotonic()
def norm(x):return ' '.join(unicodedata.normalize('NFC',x).casefold().split())
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def timeout(*a):raise TimeoutError('120 second bound')
def vm():return {k:int(v.strip().split()[0])*1024 for k,v in (l.split(':',1) for l in pathlib.Path('/proc/self/status').read_text().splitlines() if l.startswith(('VmHWM:','VmPeak:','VmRSS:')))}
def main():
 os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});resource.setrlimit(resource.RLIMIT_AS,(268435456,268435456));signal.signal(signal.SIGALRM,timeout);signal.alarm(120)
 assert shutil.disk_usage(BASE).free>=8589934592+16777216
 OUT.mkdir(exist_ok=False)
 protocol=json.loads((HERE/'conditional-agreement-protocol.json').read_text())
 paths={'protocol':HERE/'conditional-agreement-protocol.json','inputs':HERE/'inputs.json','cached':BASE/'vipi-corpus-support-inventory-20261108-r01/inventory.json','apple':BASE/'vipi-apple-delivery-20261107-r01/native-source-annotations-r01/outputs.json','android':BASE/'vipi-android-source-annotations-20261108-r01/annotations.jsonl','units':W/'phrases/dictionary-units.sqlite','variants':W/'phrases/candidates.sqlite'}
 expected={'inputs':'cb37306db9723bf39ea41204674515c890fa12186d7e6ac052db06e6d1f27b14','cached':'c52ac3eb3256803c44d38f41acb1dd318d227bae26dc33a21331201db02f735c','apple':'27fb33481bc2f6e5abf673d0817a28369658057fc3e3aee0304019e2e04e062d','android':'5de5ba4efc6ba0696ca0999ccee86640d3949ac6e4629709fe4c8f3e34fa7910','units':'8a382e08cab53e7a26095d849192508df1cff3b4ab0a55dd494fef459d414f57','variants':'54cbd4e1bc1af66b5045fb5e683b2e6e5abbd333421dd272357e061a32772747'}
 hashes={k:sha(p) for k,p in paths.items()};assert all(hashes[k]==v for k,v in expected.items())
 cached=json.loads(paths['cached'].read_text());cached_groups={(r['pair'],r['source_key']) for r in cached['groups'] if r['arm']=='grow-diag-final-and'};del cached
 inputs={c['id']:c for c in json.loads(paths['inputs'].read_text())['cases']};assert len(inputs)==116
 occurrences=[]
 def add(engine,cid,text,start,end,tag,score):
  assert inputs[cid]['text'].encode('utf-16-le')[start*2:end*2].decode('utf-16-le')==text
  if not any(x.isalpha() for x in text):return
  occurrences.append(dict(engine=engine,id=cid,key=norm(text),text=text,start=start,end=end,tag=tag,pos=protocol['mapping'][engine].get(tag),score=score))
 apple=json.loads(paths['apple'].read_text());assert len(apple['cases'])==116
 for c in apple['cases']:
  for o in c['observations']:
   if o['scheme']=='LexicalClass':add('apple',c['id'],o['substring'],o['utf16_start'],o['utf16_start']+o['utf16_length'],o['tag'],o['confidence'])
 del apple
 android_ids=set()
 with paths['android'].open() as f:
  for line in f:
   c=json.loads(line)
   if c['pass']!=0:continue
   android_ids.add(c['id'])
   for s in c['sentences']:
    for t in s['tokens']:add('android',c['id'],t['text'],t['start'],t['end'],t['pos'],t['pos_score'])
 assert android_ids==set(inputs)
 keys=sorted({o['key'] for o in occurrences})
 dd=sqlite3.connect(paths['units'].as_uri()+'?mode=ro&immutable=1',uri=True);db=sqlite3.connect(paths['variants'].as_uri()+'?mode=ro&immutable=1',uri=True);db.row_factory=sqlite3.Row
 for c in [dd,db]:c.execute('PRAGMA cache_size=-4096')
 def units(lang,key):
  r=dd.execute('SELECT evidence FROM units WHERE language=? AND key=?',(lang,key)).fetchone();return json.loads(r[0]) if r else []
 summary=collections.defaultdict(collections.Counter);lookup={};written=0;proof_count=0
 output=OUT/'key-proof-sets.jsonl'
 with output.open('x') as stream:
  for key in keys:
   source=units('en',key)
   terms=collections.defaultdict(list)
   for u in source:
    for t in u['terms']:
     if t['eligible'] and t['explicit']:terms[(u['pos'],t['sense_id'])].append((u,t))
   for pair in ['en-es','en-sw']:
    sets={s:set() for s in terms};proofs=[];emissions={};ranks={};variant_count=0
    for row in db.execute('SELECT * FROM ranked WHERE pair=? AND arm=? AND source_key=? ORDER BY distinct_components DESC,mean_lexical_score DESC,id',(pair,'grow-diag-final-and',key)):
     variant_count+=1;r=dict(row);target=units(pair.split('-')[1],r['target_key'])
     for tu in target:
      for tt in tu['terms']:
       sense=(tu['pos'],tt['sense_id'])
       if not(tt['eligible'] and tt['explicit']) or sense not in terms:continue
       for su,st in terms[sense]:
        if su['number']!=tu['number']:continue
        identity=(unicodedata.normalize('NFC',tu['surface']),tu['pos'],tu['number'],json.dumps(tu['features'],sort_keys=True),tt['reading'])
        eid=hashlib.sha256(json.dumps(identity,ensure_ascii=False).encode()).hexdigest()
        emissions[eid]=dict(face=identity[0],pos=identity[1],number=identity[2],features=tu['features'],reading=identity[4],identical=norm(identity[0])==key)
        sets[sense].add(eid);ranks.setdefault(eid,(-r['distinct_components'],-r['mean_lexical_score'],r['id'],json.dumps(identity,ensure_ascii=False)))
        proof={'sense':sense,'source_label':st['label'],'source_lexeme':su['lexeme_id'],'target_lexeme':tu['lexeme_id'],'source_surface':su['surface'],'source_number':su['number'],'source_features':su['features'],'source_mode':su['mode'],'target_mode':tu['mode'],'source_url':st['sense_source_url'],'target_url':tt['sense_source_url'],'emission':eid,'variant':r['id'],'aligned_observations':r['observations'],'components':r['distinct_components']}
        proofs.append(proof)
    def measure(pos):
     chosen={s:v for s,v in sets.items() if pos is None or s[0]==pos};vals=list(chosen.values());union=set().union(*vals) if vals else set();common=set.intersection(*vals) if vals else set()
     pick=min(common,key=lambda x:ranks[x]) if common else None;winner=min(union,key=lambda x:ranks[x]) if union else None
     return dict(source_senses=len(vals),missing_target_senses=sum(not s for s in vals),common_count=len(common),common=sorted(common),strict_union_singleton=bool(vals) and all(vals) and len(union)==1,union_count=len(union),selected=pick,selected_identical=emissions[pick]['identical'] if pick else None,frequency_winner=winner,frequency_identical=emissions[winner]['identical'] if winner else None,frequency_common=winner in common if winner else False)
    allpos=measure(None);bypos={p:measure(p) for p in sorted({s[0] for s in terms})};lookup[(pair,key)]=(allpos,bypos,emissions)
    c=summary[pair];c['all_keys']+=1;c['no_retained_units']+=not source;c['no_explicit_source_senses']+=not terms;c['no_grow_variants']+=not variant_count;c['source_senses']+=len(terms);c['missing_target_senses']+=allpos['missing_target_senses'];c['any_missing_target_sense']+=allpos['missing_target_senses']>0;c['allpos_common']+=allpos['common_count']>0;c['allpos_nonidentical_choice']+=allpos['selected_identical'] is False;c['allpos_strict_union_singleton']+=allpos['strict_union_singleton'];c['any_pos_common']+=any(x['common_count'] for x in bypos.values());c['any_pos_nonidentical_choice']+=any(x['selected_identical'] is False for x in bypos.values());c['any_pos_new_common_vs_allpos']+=not allpos['common_count'] and any(x['common_count'] for x in bypos.values());c['cached_complete_pool_keys']+=(pair,key) in cached_groups
    result=dict(pair=pair,key=key,variant_count=variant_count,allpos=allpos,bypos=bypos,emissions=emissions,sense_sets=[dict(pos=s[0],sense=s[1],emissions=sorted(v)) for s,v in sets.items()],proofs=proofs)
    payload=json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n';written+=len(payload.encode());assert written<15*1024**2;stream.write(payload);proof_count+=len(proofs)
 occsum=collections.defaultdict(collections.Counter);details=[]
 for o in occurrences:
  for pair in ['en-es','en-sw']:
   a,b,e=lookup[(pair,o['key'])];r=b.get(o['pos']) if o['pos'] else None;c=occsum[(o['engine'],pair)];c['all_token_occurrences']+=1;c['mapped_role_occurrences']+=o['pos'] is not None;c['role_without_source_senses']+=o['pos'] is not None and r is None
   if r:
    c['role_with_source_senses']+=1;c['missing_target_sense_occurrences']+=r['missing_target_senses']>0;c['conditional_common']+=r['common_count']>0;c['conditional_nonidentical_choice']+=r['selected_identical'] is False;c['new_common_vs_allpos']+=bool(r['common_count']) and not a['common_count'];c['conditional_strict_union_singleton']+=r['strict_union_singleton'];c['frequency_available']+=r['frequency_winner'] is not None;c['frequency_nonidentical_choice']+=r['frequency_identical'] is False;c['frequency_winner_outside_common']+=r['frequency_winner'] is not None and not r['frequency_common']
   if o['key'] in {'plant','book','play','too','visit','planes','fruits','flash','tech'}:details.append(dict(**o,pair=pair,allpos=a,conditional=r,emissions=e))
 result={'complete':True,'production':False,'hashes':hashes,'key_count':len(keys),'keys':keys,'proof_count':proof_count,'summary':dict(summary),'occurrence_summary':[dict(engine=k[0],pair=k[1],**v) for k,v in occsum.items()],'diagnostics':details,'proof_output':str(output),'proof_output_sha256':sha(output),'proof_output_bytes':written,'measurement':vm(),'address_space_limit':resource.getrlimit(resource.RLIMIT_AS),'cpu_affinity':sorted(os.sched_getaffinity(0))}
 payload=json.dumps(result,ensure_ascii=False,indent=2)+'\n';assert written+len(payload.encode())<16777216
 (OUT/'result.json').write_text(payload)
 return {'complete':True,'production':False,'result':str(OUT/'result.json'),'result_sha256':sha(OUT/'result.json'),'protocol_sha256':hashes['protocol'],'summary':result['summary'],'occurrence_summary':result['occurrence_summary'],'key_count':len(keys),'proof_count':proof_count,'output_bytes':written+len(payload.encode()),'measurement':vm(),'address_space_limit':resource.getrlimit(resource.RLIMIT_AS),'cpu_affinity':sorted(os.sched_getaffinity(0))}
if __name__=='__main__':
 try:r=main()
 except BaseException as e:r={'complete':False,'production':False,'error':repr(e),'measurement':vm()}
 r.update(seconds=time.monotonic()-START,code_sha256=sha(pathlib.Path(__file__)))
 (HERE/'conditional-agreement-receipt.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
