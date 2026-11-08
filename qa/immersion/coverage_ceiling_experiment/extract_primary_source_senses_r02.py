#!/usr/bin/env python3
"""Resumable bounded selected reads of retained English native dictionary senses.
Every completed 128-entry batch is durable; no entire inventory transfer/hash read.
"""
import argparse,gzip,hashlib,json,sqlite3,time
from pathlib import Path
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def emit(p,d):
 raw=(json.dumps(d,ensure_ascii=False,separators=(',',':'))+'\n').encode();assert len(raw)<64*1024**2;p.write_bytes(gzip.compress(raw,mtime=0))
def main():
 p=argparse.ArgumentParser();p.add_argument('--inventory',type=Path,required=True);p.add_argument('--selection',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--max-seconds',type=int,default=900);a=p.parse_args();a.output_dir.mkdir(exist_ok=True);started=time.monotonic();assert a.inventory.stat().st_size==4428693504
 selected=json.loads(a.selection.read_text());ids=sorted({e['lexeme'] for r in selected['rows'] for e in r['content_lexemes']});binding={'selection_sha256':sha(a.selection),'compiler_sha256':sha(Path(__file__)),'expected_inventory_sha256':'8c97e9de2ce8e94ce9754475a85eb27cd956ee0ba69491fe270376e3177ceb17'};db=sqlite3.connect(a.inventory.resolve().as_uri()+'?mode=ro&immutable=1',uri=True);db.execute('PRAGMA query_only=ON');db.execute('PRAGMA cache_size=-8192');db.execute('PRAGMA temp_store=FILE');db.set_progress_handler(lambda:int(time.monotonic()-started>a.max_seconds),10000);metadata=dict(db.execute('SELECT key,value FROM metadata'));receipts=[];entries=[];senses=[];complete=True
 for start in range(0,len(ids),128):
  group=ids[start:start+128];out=a.output_dir/f'batch-{start:05d}.json.gz'
  if out.exists():
   b=json.loads(gzip.decompress(out.read_bytes()));assert b['binding']==binding and b['ids']==group
  else:
   if time.monotonic()-started>a.max_seconds:complete=False;break
   marks=','.join('?' for _ in group)
   try:
    en=db.execute('SELECT source_line,language,headword,normalized,part_of_speech,tags,source_url FROM native_entries WHERE source_line IN ('+marks+') ORDER BY source_line',group).fetchall()
    se=db.execute('SELECT source_line,sense_index,glosses,tags,form_of,alt_of FROM native_senses WHERE source_line IN ('+marks+') ORDER BY source_line,sense_index',group).fetchall()
   except sqlite3.OperationalError as error:
    complete=False;print('bounded_read_stopped',str(error),flush=True);break
   assert len(en)==len(group) and all(r[1]=='en' for r in en);b={'binding':binding,'ids':group,'entries':en,'senses':se};emit(out,b)
  entries+=b['entries'];senses+=b['senses'];receipts.append({'file':out.name,'sha256':sha(out),'bytes':out.stat().st_size,'entries':len(b['entries']),'senses':len(b['senses'])});print('retained',len(entries),'/',len(ids),'elapsed',round(time.monotonic()-started,2),flush=True)
 db.close();result={'production':False,'training_only':True,'complete':complete and len(entries)==len(ids),'binding':binding,'fresh_whole_inventory_hash_verified':False,'identity_basis':'Exact retained read-only StorageBox route, expected historical archive identity,4,428,693,504-byte size and embedded metadata. Selected extracts get fresh hashes; no bulk source read or retired host access.','inventory_route':str(a.inventory),'inventory_bytes':a.inventory.stat().st_size,'metadata':metadata,'entry_columns':['source_line','language','headword','normalized','part_of_speech','tags','source_url'],'sense_columns':['source_line','sense_index','glosses','tags','form_of','alt_of'],'entries':entries,'senses':senses,'elapsed_seconds':time.monotonic()-started,'batches':receipts};out=a.output_dir/'selected-native-senses.json.gz';emit(out,result);print(json.dumps({'sha256':sha(out),'bytes':out.stat().st_size,'entries':len(entries),'senses':len(senses),'complete':result['complete'],'elapsed':result['elapsed_seconds']}),flush=True)
if __name__=='__main__':main()
