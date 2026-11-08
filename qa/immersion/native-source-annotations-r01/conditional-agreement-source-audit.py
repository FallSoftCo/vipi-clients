#!/usr/bin/env python3
"""Additive source-completeness audit; original scoped estimate remains frozen."""
import collections,hashlib,json,os,pathlib,resource,shutil,signal,sqlite3,time
HERE=pathlib.Path(__file__).resolve().parent;BASE=pathlib.Path('/home/ai/Development/investigations');OUT=BASE/'vipi-conditional-agreement-inventory-20261108-r01';START=time.monotonic()
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for x in iter(lambda:f.read(1048576),b''):h.update(x)
 return h.hexdigest()
def vm():return {k:int(v.strip().split()[0])*1024 for k,v in (l.split(':',1) for l in pathlib.Path('/proc/self/status').read_text().splitlines() if l.startswith(('VmHWM:','VmPeak:','VmRSS:')))}
def stop(*a):raise TimeoutError('120 second audit bound')
def main():
 os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});resource.setrlimit(resource.RLIMIT_AS,(268435456,268435456));signal.signal(signal.SIGALRM,stop);signal.alarm(120)
 assert shutil.disk_usage(BASE).free>=8589934592+16777216
 # Freeze meaning before computing audit counts. Explicit=0 is not a semantic rejection.
 freeze={'production':False,'source_completeness':'unknown for every key; retained linked pivot senses do not enumerate every native lexical meaning','strata':'distinct(POS,sense_id) per key, separately eligible_explicit/eligible_nonexplicit/ineligible_explicit/ineligible_nonexplicit; identities may appear in more than one stratum when metadata differs','native_counts':'lexemes.senses retained per source lexeme; no subtraction from linked identities, no invented unmapped sense IDs','scope':'same618 frozen keys, keyed units and source lexeme reads only; original estimate unchanged','unresolved_rule':'Any nonexplicit or ineligible source term is unresolved additional link evidence, not a known wrong translation. Count formal common emissions with this evidence separately; do not label remaining cases complete.'}
 (OUT/'source-audit-freeze.json').write_text(json.dumps(freeze,indent=2)+'\n')
 resultpath=OUT/'result.json';r=json.loads(resultpath.read_text());assert sha(resultpath)=='e95e74ca64d0b3cda91c502e415cac8ed6850705a9590b8a1ce4a5000721c6cb'
 up=BASE/'vipi-immersion-reconciliation-20261107-r01/corpus-phrase-extraction-r01/phrases/dictionary-units.sqlite';lp=BASE/'vipi-immersion-reconciliation-20261107-r01/noun-boundary-arms/d-en.sqlite'
 hashes={'units':sha(up),'source_dictionary':sha(lp),'result':sha(resultpath),'audit_freeze':sha(OUT/'source-audit-freeze.json')};assert hashes['source_dictionary']=='5b16dafff9b2a27474792104bad11195ba8aff2236c134cf0265257b92727d68'
 db=sqlite3.connect(up.as_uri()+'?mode=ro&immutable=1',uri=True);ld=sqlite3.connect(lp.as_uri()+'?mode=ro&immutable=1',uri=True);ld.row_factory=sqlite3.Row
 rows=[];total=collections.Counter();audit={}
 for key in r['keys']:
  raw=db.execute('select evidence from units where language=? and key=?',('en',key)).fetchone();units=json.loads(raw[0]) if raw else [];strata=collections.defaultdict(set);lexemes={};terms={}
  for u in units:
   lid=u['lexeme_id']
   if lid not in lexemes:lexemes[lid]=dict(ld.execute('select * from lexemes where id=?',(lid,)).fetchone())
   for t in u['terms']:
    category=('eligible' if t['eligible'] else 'ineligible')+('_explicit' if t['explicit'] else '_nonexplicit');identity=(u['pos'],t['sense_id']);strata[category].add(identity)
    terms.setdefault(identity,{'pos':identity[0],'sense_id':identity[1],'labels':set(),'categories':set()});terms[identity]['labels'].add(t['label']);terms[identity]['categories'].add(category)
  extra=set().union(*(v for k,v in strata.items() if k!='eligible_explicit'))
  item={'key':key,'source_completeness':'unknown','native_lexemes':list(lexemes.values()),'strata':{k:sorted(v) for k,v in strata.items()},'unresolved_extra_link_POS':sorted({p for p,s in extra}),'terms':[dict(v,labels=sorted(v['labels']),categories=sorted(v['categories'])) for v in terms.values()]}
  rows.append(item);audit[key]=item;total['all_keys']+=1;total['keys_without_retained_units']+=not units;total['keys_with_unresolved_extra_links']+=bool(extra);total['keys_with_native_sense_count']+=bool(lexemes)
  for k,v in strata.items():total[k+':distinct_key_pos_senses']+=len(v);total[k+':keys']+=bool(v)
  total['unique_source_lexemes_per_key_sum']+=len(lexemes)
 common=collections.defaultdict(collections.Counter)
 with open(r['proof_output']) as f:
  for line in f:
   x=json.loads(line);a=audit[x['key']];c=common[x['pair']]
   if x['allpos']['common_count']:c['allpos_common']+=1;c['allpos_common_with_unresolved_extra_links']+=bool(a['unresolved_extra_link_POS'])
   for pos,m in x['bypos'].items():
    if m['common_count']:c['pos_common_groups']+=1;c['pos_common_groups_with_unresolved_extra_links']+=pos in a['unresolved_extra_link_POS']
 output={'production':False,'hashes':hashes,'interpretation':freeze,'counts':dict(total),'formal_common_link_audit':dict(common),'keys':rows,'measurement':vm()};payload=json.dumps(output,ensure_ascii=False,indent=2)+'\n'
 assert sum(p.stat().st_size for p in OUT.iterdir() if p.is_file())+len(payload.encode())<16777216
 (OUT/'source-audit.json').write_text(payload)
 return {'complete':True,'production':False,'output':str(OUT/'source-audit.json'),'sha256':sha(OUT/'source-audit.json'),'bytes':len(payload.encode()),'counts':dict(total),'formal_common_link_audit':dict(common),'measurement':vm()}
if __name__=='__main__':
 try:r=main()
 except BaseException as e:r={'complete':False,'production':False,'error':repr(e),'measurement':vm()}
 r.update(seconds=time.monotonic()-START,code_sha256=sha(pathlib.Path(__file__)));(HERE/'conditional-agreement-source-audit-receipt.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
