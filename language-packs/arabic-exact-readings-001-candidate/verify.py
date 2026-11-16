#!/usr/bin/env python3
"""Independent candidate consistency audit; not a native or linguistic review."""
import argparse,hashlib,json,sqlite3,unicodedata,zlib
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'language-packs'))
from context_hints import lookup_key
p=argparse.ArgumentParser();p.add_argument('directory',type=Path);a=p.parse_args();d=a.directory
manifest=json.loads((d/'manifest.json').read_text());blob=zlib.decompress((d/'arabic-exact-readings.sqlite.zlib').read_bytes());assert len(blob)==manifest['expanded_bytes'] and hashlib.sha256(blob).hexdigest()==manifest['expanded_sha256']
out=sqlite3.connect(':memory:');out.deserialize(blob);assert out.execute('pragma integrity_check').fetchone()==('ok',)
source=sqlite3.connect(':memory:');raw=zlib.decompress((ROOT/'data/lexical/d-ar.sqlite.zlib').read_bytes());assert hashlib.sha256(raw).hexdigest()==manifest['source_expanded_sha256'];source.deserialize(raw);del raw
count=0
for word,reading,evidence in out.execute('select surface,reading,evidence from readings order by surface'):
 entries=json.loads(evidence);norm=lookup_key(word,'ar');rows=source.execute('select s.lexeme,s.mode,l.headword,l.target_safe from surfaces s join lexemes l on l.id=s.lexeme where s.normalized=? and s.surface=?',(norm,word)).fetchall();assert rows and all(mode==1 and head==word and safe for _,mode,head,safe in rows);assert {v[0] for v in rows}=={e['lexeme_id'] for e in entries}
 for e in entries:
  real=source.execute('select sense,reading,eligible,qualifiers from terms where lexeme=? order by sense,reading,qualifiers',(e['lexeme_id'],)).fetchall();assert real and any(x[2] for x in real);saved=sorted((t['sense_id'],t['reading'],t['eligible'],json.dumps(t['qualifiers'],ensure_ascii=False,sort_keys=True,separators=(',',':'))) for t in e['terms']);assert sorted(real)==saved;assert all(t[1]==reading for t in real)
 count+=1
assert count==manifest['counts']['accepted']
for word,expected in [('كوب','kūb'),('ضع',None),('بالوعة',None),('كوبx',None)]:
 result=out.execute('select reading from readings where surface=?',(word,)).fetchone();assert (result[0] if result else None)==expected
print(json.dumps({'integrity':'ok','all_rows_compared_to_source':count,'fixture_results':{'كوب':'kūb','ضع':None,'بالوعة':None,'كوبx':None},'scope':'static consistency only; no native, semantic or acoustic qualification'},ensure_ascii=False))
