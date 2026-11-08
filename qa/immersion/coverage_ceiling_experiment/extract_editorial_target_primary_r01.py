#!/usr/bin/env python3
"""Read selected native target entries, senses and forms from retained archive."""
import argparse,gzip,hashlib,json,sqlite3,time
from pathlib import Path

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def emit(p,d):p.write_bytes(gzip.compress(json.dumps(d,ensure_ascii=False,separators=(',',':')).encode(),mtime=0))
def main():
 p=argparse.ArgumentParser();p.add_argument('--inventory',type=Path,required=True);p.add_argument('--request',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--seconds',type=int,default=900);a=p.parse_args();a.output.mkdir(exist_ok=True);request=json.loads(a.request.read_text());selected={int(k):v for k,v in request['records'].items()};ids=sorted(selected);binding={'request_sha256':sha(a.request),'script_sha256':sha(Path(__file__)),'expected_archive_sha256':request['expected_inventory_sha256']};started=time.monotonic();assert a.inventory.stat().st_size==4428693504;db=sqlite3.connect(a.inventory.resolve().as_uri()+'?mode=ro&immutable=1',uri=True);db.execute('PRAGMA query_only=ON');db.execute('PRAGMA cache_size=-8192');db.execute('PRAGMA temp_store=FILE');db.set_progress_handler(lambda:int(time.monotonic()-started>a.seconds),10000);receipts=[];all_entries=[];all_senses=[];all_forms=[]
 for start in range(0,len(ids),32):
  group=ids[start:start+32];out=a.output/f'batch-{start:04d}.json.gz'
  if out.exists():
   b=json.loads(gzip.decompress(out.read_bytes()));assert b['binding']==binding and b['ids']==group
  else:
   if time.monotonic()-started>a.seconds:break
   marks=','.join('?' for _ in group)
   try:
    entries=db.execute('SELECT * FROM native_entries WHERE source_line IN ('+marks+') ORDER BY source_line',group).fetchall();senses=db.execute('SELECT * FROM native_senses WHERE source_line IN ('+marks+') ORDER BY source_line,sense_index',group).fetchall();forms=db.execute('SELECT * FROM native_forms WHERE source_line IN ('+marks+') ORDER BY source_line,form,tags',group).fetchall()
   except sqlite3.OperationalError as e:print('bounded_stop',str(e),flush=True);break
   assert len(entries)==len(group)
   for r in entries:assert r[1]==selected[r[0]]['language'] and r[2]==selected[r[0]]['headword'],(r,selected[r[0]])
   b={'binding':binding,'ids':group,'entries':entries,'senses':senses,'forms':forms};emit(out,b)
  receipts.append({'file':out.name,'sha256':sha(out),'bytes':out.stat().st_size});all_entries+=b['entries'];all_senses+=b['senses'];all_forms+=b['forms'];print('retained',len(all_entries),'/',len(ids),'elapsed',round(time.monotonic()-started,2),flush=True)
  (a.output/'progress.json').write_text(json.dumps({'binding':binding,'complete':False,'selected':len(ids),'completed':len(all_entries),'batches':receipts,'elapsed_seconds':time.monotonic()-started},indent=2)+'\n')
 db.close();result={'production':False,'complete':len(all_entries)==len(ids),'binding':binding,'selected_entry_count':len(ids),'whole_archive_fresh_hash_verified':False,'entry_columns':['source_line','language','headword','normalized','part_of_speech','tags','source_url'],'sense_columns':['source_line','sense_index','glosses','tags','form_of','alt_of'],'form_columns':['source_line','form','normalized','tags'],'entries':all_entries,'senses':all_senses,'forms':all_forms,'batches':receipts,'elapsed_seconds':time.monotonic()-started};emit(a.output/'selected-native-targets.json.gz',result);(a.output/'receipt.json').write_text(json.dumps({k:v for k,v in result.items() if k not in ['entries','senses','forms']},indent=2)+'\n');print('complete',result['complete'],'hash',sha(a.output/'selected-native-targets.json.gz'),flush=True)
if __name__=='__main__':main()
