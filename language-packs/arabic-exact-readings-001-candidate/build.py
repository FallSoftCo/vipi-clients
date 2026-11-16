#!/usr/bin/env python3
"""Compile conservative, inactive exact-headword readings from pinned Arabic shard.

Readings and senses are copied, never generated. Each exact surface is accepted
only after every competing attested surface row, lexeme and term agrees. This is
candidate data, not permission to display a generated translation.
"""
import argparse,collections,hashlib,json,sqlite3,unicodedata,zlib
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'language-packs'))
from context_hints import lookup_key
SOURCE=ROOT/'data/lexical/d-ar.sqlite.zlib'; CATALOG=ROOT/'data/lexical/catalog.json'
def sha(b):return hashlib.sha256(b).hexdigest()
def raw(x):return (json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
def arabic_word(s):
 return bool(s) and unicodedata.normalize('NFC',s)==s and all(unicodedata.category(c)[0] in 'LM' and ('ARABIC' in unicodedata.name(c,'') or unicodedata.category(c)[0]=='M') for c in s)
def latin_reading(s):
 return bool(s) and len(s)<=128 and all(('LATIN' in unicodedata.name(c,'') if c.isalpha() else (unicodedata.category(c)[0]=='M' or c in " '-’")) for c in s)
def build(out):
 out.mkdir(parents=True,exist_ok=False);source=SOURCE.read_bytes();catalog=json.loads(CATALOG.read_text());entry=next(x for x in catalog['files'] if x['id']=='d-ar');assert len(source)==entry['compressed_bytes'] and sha(source)==entry['compressed_sha256'];expanded=zlib.decompress(source);assert len(expanded)==entry['bytes'] and sha(expanded)==entry['sha256']
 db=sqlite3.connect(':memory:');db.deserialize(expanded);del expanded
 # Enumerate literal headwords with some target-safe entry. Normalized key is
 # only an index route; exact surface equality below remains authoritative.
 heads=db.execute('select distinct headword from lexemes where target_safe=1 order by headword').fetchall();counts=collections.Counter();accepted=[]
 for (word,) in heads:
  if not arabic_word(word):counts['not_single_arabic_word']+=1;continue
  norm=lookup_key(word,'ar');guard=db.execute('select blocked,target_blocked from guards where normalized=?',(norm,)).fetchone()
  if guard and (guard[0] or guard[1]):counts['blocked_guard']+=1;continue
  rows=db.execute('''select s.lexeme,s.mode,l.headword,l.target_safe,l.source_url from surfaces s join lexemes l on l.id=s.lexeme where s.normalized=? and s.surface=? order by s.lexeme,s.mode''',(norm,word)).fetchall()
  if not rows:counts['no_exact_surface']+=1;continue
  # A noncanonical attested form cannot borrow the headword pronunciation.
  if any(mode!=1 or head!=word or not safe for _,mode,head,safe,_ in rows):counts['competing_form_or_unsafe_lexeme']+=1;continue
  ids=sorted({r[0] for r in rows});evidence=[];all_readings=[];bad=None
  for lid in ids:
   terms=db.execute('''select t.sense,t.reading,t.eligible,t.qualifiers,s.label,s.pos,s.source_url from terms t join senses s on s.id=t.sense where t.lexeme=? order by t.sense,t.reading,t.qualifiers''',(lid,)).fetchall()
   if not terms or not any(t[2]==1 for t in terms):bad='missing_sense_or_eligible_reading';break
   if any(not latin_reading(t[1]) for t in terms):bad='missing_or_nonlatin_reading';break
   all_readings.extend(t[1] for t in terms)
   evidence.append({'lexeme_id':lid,'source_url':next(r[4] for r in rows if r[0]==lid),'terms':[{'sense_id':s,'reading':reading,'eligible':eligible,'qualifiers':json.loads(q),'label':label,'pos':pos,'source_url':url} for s,reading,eligible,q,label,pos,url in terms]})
  if bad:counts[bad]+=1;continue
  readings=set(all_readings)
  if len(readings)!=1:counts['conflicting_readings']+=1;continue
  accepted.append((word,next(iter(readings)),raw(evidence).decode().strip()));counts['accepted']+=1
 dest=sqlite3.connect(out/'arabic-exact-readings.sqlite');dest.executescript('PRAGMA page_size=4096; CREATE TABLE readings(surface TEXT PRIMARY KEY,reading TEXT NOT NULL,evidence TEXT NOT NULL) WITHOUT ROWID; CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL) WITHOUT ROWID;')
 dest.executemany('insert into readings values (?,?,?)',accepted);meta={'schema':'vipi-arabic-exact-reading-candidate-1','active':False,'source_compressed_sha256':entry['compressed_sha256'],'source_expanded_sha256':entry['sha256'],'dictionary_release':catalog['dictionary_release'],'policy':'exact-canonical-all-competitors-all-terms-unanimous-1','license':'CC-BY-SA-4.0','attribution':'Wiktionary contributors; Kaikki/Wiktextract. See ATTRIBUTION.txt.','limitations':'Supplied lexical reading only, not generated-word meaning, independent pronunciation review or runtime activation.'};dest.executemany('insert into metadata values (?,?)',[(k,json.dumps(v,ensure_ascii=False,sort_keys=True)) for k,v in meta.items()]);dest.commit();dest.execute('VACUUM');dest.close()
 blob=(out/'arabic-exact-readings.sqlite').read_bytes();compressed=zlib.compress(blob,9);(out/'arabic-exact-readings.sqlite.zlib').write_bytes(compressed);(out/'ATTRIBUTION.txt').write_bytes((ROOT/'data/lexical/ATTRIBUTION.txt').read_bytes());manifest={**meta,'counts':dict(sorted(counts.items())),'expanded_bytes':len(blob),'expanded_sha256':sha(blob),'compressed_bytes':len(compressed),'compressed_sha256':sha(compressed),'builder_sha256':sha(Path(__file__).read_bytes())};(out/'manifest.json').write_bytes(raw(manifest));print(json.dumps(manifest,ensure_ascii=False))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);build(p.parse_args().output)
