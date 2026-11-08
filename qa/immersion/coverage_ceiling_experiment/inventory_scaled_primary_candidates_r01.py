#!/usr/bin/env python3
"""Bounded build-time inventory of retained lexical links; no acceptance or runtime edits."""
import argparse,collections,hashlib,json,os,shutil,sqlite3,time,unicodedata,zlib
from pathlib import Path
Q=Path(__file__).resolve().parent
CONTENT={'noun','verb','adj','adv'};READING={'ar','ja','ko','zh'}
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(1048576):h.update(b)
 return h.hexdigest()
def u16(s):return len(s.encode('utf-16-le'))//2
def connect(p):return sqlite3.connect(p.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
def main():
 p=argparse.ArgumentParser();p.add_argument('--source-db',type=Path,required=True);p.add_argument('--retained-es-db',type=Path,required=True);p.add_argument('--catalog',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args();a.output_dir.mkdir(exist_ok=False);start=time.perf_counter();cat=json.loads(a.catalog.read_text());files={r['id']:r for r in cat['files'] if r['id'].startswith('d-')};assert sha(a.source_db)==files['d-en']['sha256'];assert sha(a.retained_es_db)==files['d-es']['sha256'];assert shutil.disk_usage(a.output_dir).free>8*1024**3+max(r['bytes'] for r in files.values())
 freq=json.loads((Q/'scaled-training-source3000-r01.json').read_text());src=connect(a.source_db);by_sense=collections.defaultdict(set);source_rows=[];source_counts=collections.Counter()
 for f in freq['rows']:
  word=f['source'];surfaces=src.execute('SELECT l.id,l.headword,l.pos,l.source_safe,l.source_url,s.surface,s.start,s.end,s.features,s.number FROM surfaces s JOIN lexemes l ON l.id=s.lexeme WHERE s.normalized=?',(word,)).fetchall();whole=[r for r in surfaces if r[6]==0 and r[7]==u16(r[5])];content={r[:5] for r in whole if r[2] in CONTENT};senses=set();positions={r[2] for r in whole};linked=[]
  for lexeme,head,pos,safe,url in sorted(content):
   terms=src.execute('SELECT t.sense,se.label,t.eligible,t.qualifiers,se.source_url FROM terms t JOIN senses se ON se.id=t.sense WHERE t.lexeme=?',(lexeme,)).fetchall()
   for sid,label,eligible,qualifiers,senseurl in terms:
    by_sense[sid].add((word,lexeme,head,pos,label,url,senseurl,eligible,qualifiers));senses.add(sid)
   linked.append({'lexeme':lexeme,'headword':head,'pos':pos,'legacy_source_safe':bool(safe),'primary_source_url':url,'sense_links':len(terms),'complete_surfaces':sorted({(r[5],r[8],r[9]) for r in whole if r[0]==lexeme})})
  partition='no_surface' if not surfaces else 'partial_surface_only' if not whole else 'no_content_pos' if not content else 'content_without_sense_link' if not senses else 'content_sense_candidates';source_counts[partition]+=1
  source_rows.append(dict(f,source_partition=partition,parts_of_speech=sorted(positions),mixed_content_function_or_name=bool(content) and bool(positions-CONTENT),content_lexemes=linked,distinct_linked_senses=len(senses),partial_surface_records=len(surfaces)-len(whole)))
 sourcepath=a.output_dir/'source-inventory.json';sourcepath.write_text(json.dumps({'production':False,'training_only':True,'input_frequency_sha256':sha(Q/'scaled-training-source3000-r01.json'),'source_db_sha256':sha(a.source_db),'counts':dict(source_counts),'rows':source_rows},ensure_ascii=False,indent=2)+'\n')
 outdb=a.output_dir/'primary-candidates.sqlite';out=sqlite3.connect(outdb);out.executescript('CREATE TABLE candidates(source TEXT,source_lexeme INTEGER,source_head TEXT,source_pos TEXT,sense TEXT,sense_label TEXT,source_url TEXT,sense_url TEXT,target_language TEXT,target_lexeme INTEGER,target TEXT,target_pos TEXT,reading TEXT,legacy_source_eligible INTEGER,source_qualifiers TEXT,legacy_target_eligible INTEGER,target_qualifiers TEXT,target_url TEXT,complete_target_head INTEGER,reading_present INTEGER,pos_compatible INTEGER,PRIMARY KEY(source,source_lexeme,sense,target_language,target_lexeme,reading,source_qualifiers,target_qualifiers)) WITHOUT ROWID;')
 summaries={};receipts=[]
 for ident,record in sorted(files.items()):
  if ident=='d-en':continue
  lang=ident[2:];temporary=lang!='es';path=a.output_dir/'scratch-target.sqlite' if temporary else a.retained_es_db
  if temporary:
   compressed=a.catalog.parent/record['file'];assert sha(compressed)==record['compressed_sha256'];decoder=zlib.decompressobj();h=hashlib.sha256();size=0
   with compressed.open('rb') as inf,path.open('xb') as dest:
    while b:=inf.read(262144):
     value=decoder.decompress(b);size+=len(value);assert size<=record['bytes'];h.update(value);dest.write(value)
    value=decoder.flush();size+=len(value);h.update(value);dest.write(value)
   assert decoder.eof and size==record['bytes'] and h.hexdigest()==record['sha256']
  db=connect(path);matching=[];heads={}
  for lexeme,head,pos,url,sid,reading,eligible,qualifiers in db.execute('SELECT l.id,l.headword,l.pos,l.source_url,t.sense,t.reading,t.eligible,t.qualifiers FROM terms t JOIN lexemes l ON l.id=t.lexeme'):
   if sid not in by_sense:continue
   matching.append((lexeme,head,pos,url,sid,reading,eligible,qualifiers));heads[lexeme]=head
  complete=set()
  for lexeme,surface,begin,end in db.execute('SELECT lexeme,surface,start,end FROM surfaces'):
   if lexeme in heads and begin==0 and end==u16(surface) and surface==heads[lexeme] and not surface.startswith('-') and not surface.endswith('-'):complete.add(lexeme)
  states=collections.defaultdict(set);sensecounts=collections.defaultdict(set);targetheads=collections.defaultdict(set);rows_added=0
  for lexeme,head,pos,url,sid,reading,eligible,qualifiers in matching:
   for source,slex,shead,spos,label,surl,senseurl,selig,squal in by_sense[sid]:
    compatible=spos==pos and pos in CONTENT;whole=lexeme in complete;hasreading=bool(reading.strip()) if lang in READING else True;states[source].add('linked');sensecounts[source].add(sid);targetheads[source].add((head,reading))
    if compatible:states[source].add('pos_compatible')
    if compatible and whole:states[source].add('complete_head')
    if compatible and whole and hasreading:states[source].add('candidate_for_sense_review')
    out.execute('INSERT OR IGNORE INTO candidates VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(source,slex,shead,spos,sid,label,surl,senseurl,lang,lexeme,head,pos,reading,selig,squal,eligible,qualifiers,url,int(whole),int(hasreading),int(compatible)));rows_added+=1
  out.commit();partitions=collections.Counter();available=[]
  for source in source_rows:
   w=source['source'];state=states[w]
   if source['source_partition']!='content_sense_candidates':part='source_unavailable_or_noncontent'
   elif not state:part='no_target_sense_link'
   elif 'pos_compatible' not in state:part='no_matching_content_pos'
   elif 'complete_head' not in state:part='complete_head_surface_unproven_or_bound'
   elif 'candidate_for_sense_review' not in state:part='reading_missing'
   else:part='requires_sense_context_review'
   partitions[part]+=1
   if part=='requires_sense_context_review':available.append({'source':w,'rank':source['rank'],'TRAIN_occurrences':source['occurrences'],'linked_senses':len(sensecounts[w]),'target_head_reading_candidates':len(targetheads[w]),'source_pos_mix':source['mixed_content_function_or_name']})
  summary={'source_forms':len(source_rows),'partition':dict(partitions),'candidate_source_forms':len(available),'with_multiple_linked_senses':sum(r['linked_senses']>1 for r in available),'with_multiple_target_head_reading_candidates':sum(r['target_head_reading_candidates']>1 for r in available),'with_source_pos_mix':sum(r['source_pos_mix'] for r in available),'first40_candidate_sources':available[:40],'all_candidate_source_forms':available,'primary_candidate_rows':out.execute('select count(*) from candidates where target_language=?',(lang,)).fetchone()[0]};summaries[lang]=summary;receipts.append({'language':lang,'expanded_sha256':record['sha256'],'expanded_bytes':record['bytes'],'source_shard_retained':not temporary,'temporary_retired_after_read':temporary});db.close()
  if temporary:path.unlink()
  print(lang,json.dumps({k:v for k,v in summary.items() if k not in ['first40_candidate_sources','all_candidate_source_forms']}),flush=True)
 out.close();src.close();result={'production':False,'semantic_accuracy_claim':False,'training_only':True,'source_frequency_sha256':sha(Q/'scaled-training-source3000-r01.json'),'catalog_sha256':sha(a.catalog),'compiler_sha256':sha(Path(__file__)),'source_partition':dict(source_counts),'targets':summaries,'source_payload_receipts':receipts,'candidate_index_sha256':sha(outdb),'candidate_index_bytes':outdb.stat().st_size,'elapsed_seconds':time.perf_counter()-start,'limits':['Candidates are inherited primary dictionary/sense links, not accepted mappings or useful conversation coverage.','Legacy safety/eligibility booleans retained as evidence, not blanket uniqueness-based admission.','Nonempty reading is availability only; pronunciation/context still needs review.','Target head-surface proof is narrower than all valid inflected forms; failures are explicit and not language impossibility.','No data/matcher/provider/app change, no held-out source used to rank inventory.','One target scratch at a time, verified exact source hashes, no downloads/new models/new services.']};(a.output_dir/'inventory-summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print('DONE',round(result['elapsed_seconds'],2),result['candidate_index_bytes'],sha(a.output_dir/'inventory-summary.json'),flush=True)
if __name__=='__main__':main()
