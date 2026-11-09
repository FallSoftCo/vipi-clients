#!/usr/bin/env python3
"""Keyed packed cross-check and aggregate retained provenance; no changes."""
import collections,hashlib,json,sqlite3,time,resource,os,signal
from pathlib import Path
W=Path('/home/ai/Development/investigations/vipi-lexical-relation-provenance-20261109-r01')
D=Path('/home/ai/Development/investigations/vipi-immersion-reconciliation-20261107-r01/noun-boundary-arms')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 start=time.monotonic();os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});resource.setrlimit(resource.RLIMIT_AS,(1024**3,)*2);signal.alarm(120)
 c=json.loads((W/'cohort-freeze.json').read_text());e=json.loads((W/'trace-r01/evidence.json').read_text());out=W/'packed-trace-r01';out.mkdir(exist_ok=False)
 records=[];meta={}
 for lang,ids in [('en',{15812,15814,3288}),('es',{161656})]:
  db=sqlite3.connect((D/f'd-{lang}.sqlite').as_uri()+'?mode=ro&immutable=1',uri=True);db.row_factory=sqlite3.Row;db.execute('PRAGMA query_only=ON');meta[lang]=dict(db.execute('SELECT key,value FROM metadata'))
  for ident in sorted(ids):
   records.append({'language':lang,'id':ident,'lexeme':dict(db.execute('SELECT * FROM lexemes WHERE id=?',(ident,)).fetchone()),'terms':[dict(r) for r in db.execute('SELECT t.*,s.label,s.pos,s.explicit,s.source_url FROM terms t JOIN senses s ON s.id=t.sense WHERE t.lexeme=? ORDER BY t.sense,t.reading',(ident,))]})
  db.close()
 traces={t['source_line']:t for t in e['compiler_traces']};zero=[];counter=collections.Counter();resolutions=collections.Counter()
 for f in c['forms']:
  t=traces[f['form']['lexeme_id']]
  if f['strata']['zero_terms']:zero.append({'language':f['language'],'form_id':f['form']['form_id'],'surface':f['form']['surface'],'lexeme_id':t['source_line'],'trace':t})
  for k in ('zero_terms','complete_supported'):
   counter[k]+=bool(f['strata'][k])
  counter['with_eligible_nonexplicit_native_terms']+=bool(f['strata']['eligible_native_gloss_terms'])
 for t in e['compiler_traces']:
  if t['language']=='es':
   counter['spanish_entries']+=1;counter['spanish_counterparts_accepted']+=t['counterparts_result'] is not None
   for r in t['english_resolutions']:resolutions[r['reason']]+=1
 result={'inputs':{str(p):digest(p) for p in [W/'cohort-freeze.json',W/'trace-r01/evidence.json']},'packed_metadata':meta,'diagnostic_packed_records':records,'form_counts':dict(counter),'spanish_resolver_counts':dict(resolutions),'all_zero_term_forms':zero,'limits':'Overlapping form strata; compiler trace is current-source reconstruction, packed records authoritative for observed terms. No complete dictionary-sense or occurrence correctness claim.'}
 p=out/'evidence.json';p.write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+'\n');assert p.stat().st_size<8*1024**2
 receipt={'complete':True,'script_sha256':digest(Path(__file__)),'output_sha256':digest(p),'bytes':p.stat().st_size,'seconds':time.monotonic()-start,'VmHWM_bytes':int(next(s.split()[1] for s in Path('/proc/self/status').read_text().splitlines() if s.startswith('VmHWM:')))*1024}
 (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt));print(json.dumps(result['form_counts']));print(json.dumps(result['spanish_resolver_counts']))
if __name__=='__main__':main()
