#!/usr/bin/env python3
"""Supplement retained candidate links with native target lexical flags; no admission."""
import argparse,gzip,hashlib,json,shutil,sqlite3,zlib
from pathlib import Path
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(1048576):h.update(b)
 return h.hexdigest()
def ro(p):return sqlite3.connect(p.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
def main():
 p=argparse.ArgumentParser();p.add_argument('--catalog',type=Path,required=True);p.add_argument('--candidates',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();cat=json.loads(a.catalog.read_text());db=ro(a.candidates);wanted={lang:{r[0] for r in db.execute('SELECT DISTINCT target_lexeme FROM candidates WHERE target_language=?',(lang,))} for (lang,) in db.execute('SELECT DISTINCT target_language FROM candidates')};db.close();targets={};receipts=[];assert shutil.disk_usage(a.output.parent).free>9*1024**3
 for f in cat['files']:
  if not f['id'].startswith('d-') or f['id'][2:] not in wanted:continue
  lang=f['id'][2:];compressed=a.catalog.parent/f['file'];assert sha(compressed)==f['compressed_sha256'];scratch=a.output.parent/'target-metadata-scratch.sqlite';assert not scratch.exists();dec=zlib.decompressobj();h=hashlib.sha256();size=0
  with compressed.open('rb') as inf,scratch.open('xb') as out:
   while b:=inf.read(262144):
    v=dec.decompress(b);size+=len(v);assert size<=f['bytes'];h.update(v);out.write(v)
   v=dec.flush();size+=len(v);h.update(v);out.write(v)
  assert dec.eof and size==f['bytes'] and h.hexdigest()==f['sha256'];d=ro(scratch);rows={str(i):{'headword':head,'pos':pos,'target_lexical_safe':bool(safe),'modern_native_sense_count':count,'source_url':url} for i,head,pos,safe,count,url in d.execute('SELECT id,headword,pos,target_safe,senses,source_url FROM lexemes') if i in wanted[lang]};assert len(rows)==len(wanted[lang]);d.close();scratch.unlink();targets[lang]=rows;receipts.append({'language':lang,'sha256':f['sha256'],'bytes':size,'selected_lexemes':len(rows)});print(lang,len(rows),flush=True)
 result={'production':False,'candidate_sha256':sha(a.candidates),'catalog_sha256':sha(a.catalog),'compiler_sha256':sha(Path(__file__)),'source_receipts':receipts,'targets':targets};a.output.write_bytes(gzip.compress((json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n').encode(),mtime=0));print(sha(a.output),a.output.stat().st_size)
if __name__=='__main__':main()
