"""Deterministic existing candidate export; census mode writes no runtime catalog."""
import argparse,collections,hashlib,json,os,pathlib,resource,shutil,signal,socket,sqlite3,time,zlib
R=pathlib.Path('/srv/fallsoft/staging/vipi-native-baseline-catalog-20261109-r01');M=1024**2
SCHEMA='''PRAGMA application_id=1447645257; PRAGMA user_version=1;
PRAGMA page_size=4096; PRAGMA journal_mode=DELETE; PRAGMA temp_store=FILE; PRAGMA foreign_keys=ON;
CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE candidates(id TEXT PRIMARY KEY,source_key TEXT NOT NULL,context_id TEXT NOT NULL,baseline INTEGER NOT NULL,
 conditional INTEGER NOT NULL,train_rank INTEGER NOT NULL,record_json TEXT NOT NULL,audit_json TEXT NOT NULL,
 record_sha256 TEXT NOT NULL,audit_sha256 TEXT NOT NULL) WITHOUT ROWID;
CREATE INDEX candidate_source ON candidates(source_key,id);
CREATE TABLE head_keys(head_id TEXT NOT NULL REFERENCES candidates(id),source_key TEXT NOT NULL,PRIMARY KEY(head_id,source_key)) WITHOUT ROWID;
CREATE TABLE evidence(id TEXT PRIMARY KEY,kind TEXT NOT NULL,value_json TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE head_evidence(head_id TEXT NOT NULL REFERENCES candidates(id),kind TEXT NOT NULL,identity TEXT NOT NULL,
 evidence_id TEXT NOT NULL REFERENCES evidence(id),PRIMARY KEY(head_id,kind,identity,evidence_id)) WITHOUT ROWID;
CREATE TABLE known_families(source TEXT PRIMARY KEY,family_id TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE source_roles(source TEXT PRIMARY KEY,roles_json TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE function_words(source TEXT PRIMARY KEY) WITHOUT ROWID;
'''
def enc(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(x):return hashlib.sha256(enc(x).encode()).hexdigest()
def sha(p):
 with open(p,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def ro(p):
 d=sqlite3.connect(pathlib.Path(p).as_uri()+'?mode=ro&immutable=1',uri=True);d.execute('PRAGMA query_only=ON');d.execute('PRAGMA cache_size=-8192');return d

def collect(p):
 path=lambda k:p['inputs'][k]['path'];catalog=ro(path('catalog'));heads=ro(path('heads'));context=ro(path('context_pack'));lookup=json.loads(pathlib.Path(path('lookup')).read_text());freq=json.loads(pathlib.Path(path('fixed_keys')).read_text());rank={v['source_key']:i for i,v in enumerate(sorted(freq['unigram_keys']+freq['multiword_keys'],key=lambda v:(-v['source_message_frequency'],-v['occurrence_frequency'],v['source_key'])))};tables=collections.defaultdict(dict);proofs={};counts=collections.Counter();selected={};proofbytes=0
 def add(table,key,row):
  old=tables[table].get(key);assert old is None or old==row;tables[table][key]=row
 def evidence(hid,kind,identity,value):
  raw=enc(value);eid=digest([kind,value]);add('evidence',eid,(eid,kind,raw));edge=(hid,kind,identity,eid);add('head_evidence',edge,edge)
 for hid,key,baseline,experimental,raw,auditraw in catalog.execute('SELECT id,source_key,baseline,experimental,record,audit FROM heads WHERE baseline=1 OR experimental=1 ORDER BY id'):
  h=json.loads(raw);audit=json.loads(auditraw);assert h['id']==hid and h['source_key']==key;assert not baseline or experimental;assert not audit['experimental_competing_geometry'];selected[hid]=h;counts['ordinary' if baseline else 'conditional']+=1;counts['ordinary_record_UTF8_bytes' if baseline else 'conditional_record_UTF8_bytes']+=len(raw.encode());assert h['source_context_token_text'] and 0<=h['source_focus_relative_tokens'][0]<h['source_focus_relative_tokens'][1]<=len(h['source_context_token_text'])
  add('candidates',hid,(hid,key,h['context_id'],baseline,int(not baseline),rank.get(key,10**9),raw,auditraw,hashlib.sha256(raw.encode()).hexdigest(),hashlib.sha256(auditraw.encode()).hexdigest()))
 # Each retained context is read once; no entire rejected proof DB traversal/copy.
 grouped=collections.defaultdict(list)
 for hid,h in selected.items():grouped[h['context_id']].append((hid,h))
 for cid,items in sorted(grouped.items()):
  row=heads.execute('SELECT proof FROM contexts WHERE id=?',(cid,)).fetchone();assert row;blob=row[0];original=json.loads(zlib.decompress(blob));proofbytes+=len(blob);index={h['head_id']:h for h in original['result']['heads']};proofs[cid]={'blob_sha256':hashlib.sha256(blob).hexdigest(),'selected_heads':sorted(hid for hid,_ in items)}
  for hid,h in items:
   proof=index[h['head_id']];raw,auditraw=tables['candidates'][hid][6:8];audit=json.loads(auditraw);assert audit['original_proof_blob_sha256']==proofs[cid]['blob_sha256'];assert proof['source_unit_id']==audit['source_unit_id'];assert proof['target_text']==h['target_face'];assert proof['head_id']==audit['head_id'];baseline=bool(tables['candidates'][hid][3]);eligible=[s for s in proof['shared_senses'] if s['structural_eligible']]
   if baseline:
    assert eligible==h['head_shared_senses'];assert proof['readings']==h['head_readings'];old=heads.execute('SELECT record FROM heads WHERE id=?',(hid,)).fetchone();assert old and old[0]==raw
   else:
    assert lookup['original_head_records'][hid]==h;guard=audit['source_guard'];assert guard['reason']=='name' and guard['blocked'] and not guard['target_blocked'];override={tuple(v[k] for k in ['source_form_id','target_form_id','source_term_id','target_term_id']) for v in audit['override_links']};assert override=={tuple(v) for v in lookup['original_override_links'][hid]}
   for side in ['source','target']:
    for f in proof[side+'_forms']:
     evidence(hid,side+'_form',f['form_id'],{k:v for k,v in f.items() if k!='terms'})
     for term in f['terms']:evidence(hid,side+'_term',f['form_id']+':'+term['term_id'],term)
   # Full original link reasons/readings retained; eligibility is never inferred from noun tags.
   for link in proof['shared_senses']:evidence(hid,'shared_link',digest(link),link)
   evidence(hid,'head_policy',proof['head_id'],{k:proof[k] for k in ['source_unit_id','target_unit_id','source_tokens','target_tokens','source_utf16','target_utf16','mutual_anchor','crossing_union_edges','source_mask_ids','target_mask_ids','reasons','structural_eligible']})
 for hid,keys in sorted(lookup['head_keys'].items()):
  assert hid in selected and not tables['candidates'][hid][3]
  for key in keys:add('head_keys',(hid,key),(hid,key))
 for table in ['known_families','source_roles','function_words']:
  for row in context.execute('SELECT * FROM '+table+' ORDER BY 1'):add(table,row[0],row)
 metadata={'kind':'vipi.source-candidate-catalog','schema':'1','source':'en','target':'es','permission':'disabled_research_only','context_pack_sha256':p['inputs']['context_pack']['sha256'],'source_manifest_sha256':digest(p['inputs']),'policy_sha256':p['contract_sha256'],'known_state':'caller-supplied only; frequency controls are not user knowledge','normalizer':'frozen NFC+casefold+whitespace; original UTF16 geometry','candidate_order':'ordinary prefix in original native-window order then id; conditional appended in original window/id order','mask_policy':'full independent dictionary recognition; never inferred from candidate availability; no mask override','role_policy':'ordinary original NOUN/ADJ/ADV contract; conditional lowercase/content/exact NOUN; live snapshot required; tag never grants display','context_policy':'original head context needed before head_keys; longest winner then exact eligible head; preserve no-head winners/no shorter rescue'}
 for lang in ['en','es']:
  d=ro(path('dictionary_'+lang));metadata['dictionary_'+lang+'_metadata_json']=enc(dict(d.execute('SELECT key,value FROM metadata')));metadata['dictionary_'+lang+'_sha256']=p['inputs']['dictionary_'+lang]['sha256'];d.close()
 for k,v in sorted(metadata.items()):add('metadata',k,(k,v))
 counts.update(contexts_read=len(grouped),compressed_proof_bytes_read=proofbytes,source_context_keys=len({h['source_key'] for h in selected.values()}),conditional_heads_with_keys=len(lookup['head_keys']),conditional_heads_without_keys=sum(not row[3] and hid not in lookup['head_keys'] for hid,row in tables['candidates'].items()))
 catalog.close();heads.close();context.close();return {t:[row for _,row in sorted(rs.items())] for t,rs in tables.items()},proofs,dict(counts)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['export']);a=ap.parse_args();assert socket.gethostname()=='fallsoft-production-20261106';start=time.monotonic();os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});os.nice(10);resource.setrlimit(resource.RLIMIT_AS,(1024**3,)*2);signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('120s')));signal.alarm(120);p=json.loads((R/'protocol-r02.json').read_text());out=R/(a.stage+'-r02');out.mkdir(exist_ok=False);receipt={'complete':False,'protocol_sha256':sha(R/'protocol-r02.json')}
 try:
  assert sha(__file__)==p['code_sha256'];assert sha(R/'CONTRACT_R02.md')==p['execution_contract_sha256'];assert shutil.disk_usage(R).free>8*1024**3+768*M
  if a.stage=='export':
   approval=json.loads((R/'root-export-approval-r02.json').read_text());assert approval['protocol_sha256']==sha(R/'protocol-r02.json') and approval['code_sha256']==sha(__file__) and approval['run_export'] is True
  for k,v in p['inputs'].items():assert sha(v['path'])==v['sha256'],k
  tables,proofs,counts=collect(p);prior=json.loads((R/'census/receipt.json').read_text());assert prior['complete'] and sha(R/'census/receipt.json')==p['parent_census_sha256'];assert digest(tables)==prior['logical_rows_sha256'];rows={t:len(v) for t,v in tables.items()};logical={t:sum(len(enc(row).encode()) for row in v) for t,v in tables.items()};receipt.update(counts=counts,table_rows=rows,logical_UTF8_bytes=logical,logical_rows_sha256=digest(tables),max_row_UTF8_bytes=max(len(enc(row).encode()) for v in tables.values() for row in v),proof_manifest_bytes=len(enc(proofs).encode()))
  if a.stage=='export':
   hashes=[]
   for filename in ['catalog.sqlite','determinism-check.sqlite']:
    d=sqlite3.connect(out/filename);d.executescript(SCHEMA);d.execute('PRAGMA max_page_count=65536')
    for t in ['metadata','candidates','head_keys','evidence','head_evidence','known_families','source_roles','function_words']:
     v=tables[t]
     if v:d.executemany('INSERT INTO '+t+' VALUES('+','.join('?' for _ in v[0])+')',v)
    d.commit();assert d.execute('PRAGMA integrity_check').fetchone()[0]=='ok' and not d.execute('PRAGMA foreign_key_check').fetchall()
    for t,v in tables.items():assert sorted(d.execute('SELECT * FROM '+t).fetchall(),key=enc)==sorted(v,key=enc)
    d.close();hashes.append(sha(out/filename))
   assert hashes[0]==hashes[1];(out/'determinism-check.sqlite').unlink();manifest={'schema':'vipi.source-candidate-manifest.1','database_sha256':hashes[0],'database_bytes':(out/'catalog.sqlite').stat().st_size,'table_counts':rows,'table_logical_sha256':{t:digest(v) for t,v in tables.items()},'dependencies':p['inputs'],'contract_sha256':p['contract_sha256'],'permission':'disabled_research_only','signature':None,'trust':'Development manifest requires externally pinned manifest SHA; self-reported hash is not trust'};(out/'manifest.json').write_text(enc(manifest)+'\n');(out/'proof-manifest.json').write_text(enc(proofs)+'\n');receipt['database_sha256']=hashes[0]
  receipt['complete']=True
 except BaseException as e:receipt['error']=repr(e);raise
 finally:
  receipt.update(seconds=time.monotonic()-start,VmHWM_bytes=int(next(s.split()[1] for s in pathlib.Path('/proc/self/status').read_text().splitlines() if s.startswith('VmHWM:')))*1024,sqlite_version=sqlite3.sqlite_version);raw=(json.dumps(receipt,indent=2)+'\n').encode();assert len(raw)<4*M;(out/'receipt.json').write_bytes(raw);print(enc(receipt),flush=True)
if __name__=='__main__':main()
