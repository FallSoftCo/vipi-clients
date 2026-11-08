#!/usr/bin/env python3
"""Read selected exact English entry IDs from the retained read-only inventory.
No bulk copy/hash read; historical archive hash is an expected identity, not a fresh hash.
"""
import argparse,gzip,hashlib,json,sqlite3,time
from pathlib import Path
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--inventory',type=Path,required=True);p.add_argument('--selection',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();started=time.monotonic();assert a.inventory.stat().st_size==4428693504
 selected=json.loads(a.selection.read_text());ids=sorted({e['lexeme'] for r in selected['rows'] for e in r['content_lexemes']});db=sqlite3.connect(a.inventory.resolve().as_uri()+'?mode=ro&immutable=1',uri=True);db.execute('PRAGMA query_only=ON');db.execute('PRAGMA cache_size=-8192');db.execute('PRAGMA temp_store=FILE');db.set_progress_handler(lambda: int(time.monotonic()-started>240),10000)
 metadata=dict(db.execute('SELECT key,value FROM metadata'));entries=[];senses=[];forms=[]
 for start in range(0,len(ids),256):
  group=ids[start:start+256];marks=','.join('?' for _ in group)
  entries.extend(db.execute('SELECT source_line,language,headword,normalized,part_of_speech,tags,source_url FROM native_entries WHERE source_line IN ('+marks+') ORDER BY source_line',group).fetchall())
  senses.extend(db.execute('SELECT source_line,sense_index,glosses,tags,form_of,alt_of FROM native_senses WHERE source_line IN ('+marks+') ORDER BY source_line,sense_index',group).fetchall())
  forms.extend(db.execute('SELECT source_line,form,normalized,tags FROM native_forms WHERE source_line IN ('+marks+') ORDER BY source_line,form,tags',group).fetchall())
  assert time.monotonic()-started<=240,'bounded read deadline'
  print('selected',min(start+256,len(ids)),'/',len(ids),'elapsed',round(time.monotonic()-started,2),flush=True)
 db.close();assert len(entries)==len(ids);assert all(r[1]=='en' for r in entries)
 result={'production':False,'training_only':True,'expected_inventory_sha256':'8c97e9de2ce8e94ce9754475a85eb27cd956ee0ba69491fe270376e3177ceb17','fresh_whole_inventory_hash_verified':False,'identity_basis':'Exact retained read-only StorageBox route, expected historical archive identity,4,428,693,504-byte size and embedded metadata. No bulk source read or old-host access. Selected output gets its own fresh hash.','inventory_route':str(a.inventory),'inventory_bytes':a.inventory.stat().st_size,'selection_sha256':sha(a.selection),'compiler_sha256':sha(Path(__file__)),'metadata':metadata,'entry_columns':['source_line','language','headword','normalized','part_of_speech','tags','source_url'],'sense_columns':['source_line','sense_index','glosses','tags','form_of','alt_of'],'form_columns':['source_line','form','normalized','tags'],'entries':entries,'senses':senses,'forms':forms,'elapsed_seconds':time.monotonic()-started}
 raw=(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n').encode();assert len(raw)<64*1024**2
 a.output.write_bytes(gzip.compress(raw,mtime=0));print(json.dumps({'sha256':sha(a.output),'bytes':a.output.stat().st_size,'uncompressed_bytes':len(raw),'entries':len(entries),'senses':len(senses),'forms':len(forms),'elapsed':result['elapsed_seconds']}),flush=True)
if __name__=='__main__':main()
