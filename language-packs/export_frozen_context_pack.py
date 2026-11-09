#!/usr/bin/env python3
"""Export frozen research evidence; never grants runtime/display authorization."""
import argparse,collections,hashlib,json,os,pathlib,resource,shutil,signal,socket,sqlite3,time
R=pathlib.Path('/srv/fallsoft/staging/vipi-native-context-pack-20261109-r01');M=1024**2
SCHEMA='''PRAGMA application_id=1447645257; PRAGMA user_version=1;
PRAGMA page_size=4096; PRAGMA journal_mode=DELETE; PRAGMA temp_store=FILE;
PRAGMA foreign_keys=ON;
CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE rules(id TEXT PRIMARY KEY,source_key TEXT NOT NULL,tokens_json TEXT NOT NULL,focus_offset INTEGER NOT NULL,
 length INTEGER NOT NULL,target TEXT NOT NULL,ratio REAL,winner_components INTEGER NOT NULL,winner_weight REAL NOT NULL,
 source_record_sha256 TEXT NOT NULL,permission TEXT NOT NULL CHECK(permission='conditional_research_only')) WITHOUT ROWID;
CREATE INDEX rule_focus ON rules(source_key,length DESC,id);
CREATE TABLE heads(id TEXT PRIMARY KEY,context_id TEXT NOT NULL,source_key TEXT NOT NULL,tokens_json TEXT NOT NULL,
 focus_json TEXT NOT NULL,target TEXT NOT NULL,readings_json TEXT NOT NULL,pos_json TEXT NOT NULL,fixed INTEGER NOT NULL,
 train_rank INTEGER NOT NULL,source_record_sha256 TEXT NOT NULL,permission TEXT NOT NULL CHECK(permission='conditional_source_name_only')) WITHOUT ROWID;
CREATE TABLE rule_heads(rule_id TEXT NOT NULL REFERENCES rules(id),head_id TEXT NOT NULL REFERENCES heads(id),
 support_components INTEGER NOT NULL,audit_ref TEXT NOT NULL,PRIMARY KEY(rule_id,head_id)) WITHOUT ROWID;
CREATE TABLE forms(id TEXT PRIMARY KEY,language TEXT NOT NULL,lexeme INTEGER NOT NULL,surface TEXT NOT NULL,
 form_range_json TEXT NOT NULL,number INTEGER NOT NULL,mode INTEGER NOT NULL,features_json TEXT NOT NULL,
 headword TEXT NOT NULL,pos TEXT NOT NULL,source_safe INTEGER NOT NULL,target_safe INTEGER NOT NULL,
 complete INTEGER NOT NULL,original_reasons_json TEXT NOT NULL,source_record_sha256 TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE terms(id TEXT PRIMARY KEY,sense_id TEXT NOT NULL,reading TEXT NOT NULL,eligible INTEGER NOT NULL,
 explicit INTEGER NOT NULL,qualifiers_json TEXT NOT NULL,original_reasons_json TEXT NOT NULL,source_record_sha256 TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE links(rule_id TEXT NOT NULL,head_id TEXT NOT NULL,source_form TEXT NOT NULL REFERENCES forms(id),
 target_form TEXT NOT NULL REFERENCES forms(id),source_term TEXT NOT NULL REFERENCES terms(id),target_term TEXT NOT NULL REFERENCES terms(id),
 PRIMARY KEY(rule_id,head_id,source_form,target_form,source_term,target_term),
 FOREIGN KEY(rule_id,head_id) REFERENCES rule_heads(rule_id,head_id)) WITHOUT ROWID;
CREATE TABLE known_families(source TEXT PRIMARY KEY,family_id TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE source_roles(source TEXT PRIMARY KEY,roles_json TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE function_words(source TEXT PRIMARY KEY) WITHOUT ROWID;
'''
def enc(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(x):return hashlib.sha256(enc(x).encode()).hexdigest()
def sha(p):
 with open(p,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def ro(p):
 c=sqlite3.connect(pathlib.Path(p).as_uri()+'?mode=ro&immutable=1',uri=True);c.execute('PRAGMA query_only=ON');return c
def build_rows(p):
 import ast
 path=lambda k:pathlib.Path(p['inputs'][k]['path'])
 lookup=json.loads(path('lookup').read_text());data=json.loads(path('dataset').read_text());control=json.loads(path('family_control').read_text());freq=json.loads(path('fixed_keys').read_text());base=json.loads(path('content_baseline').read_text());tree=ast.parse(path('old_projector').read_text());cl=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Producer');init=next(n for n in cl.body if isinstance(n,ast.FunctionDef) and n.name=='__init__');update=next(n for n in ast.walk(init) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='update' and isinstance(n.func.value,ast.Attribute) and n.func.value.attr=='function');function={e['source'] for pair in base['pairs'].values() for e in pair['entries'] if e['category']=='function'}|ast.literal_eval(update.args[0]);ranks={x['source_key']:i for i,x in enumerate(sorted(freq['unigram_keys']+freq['multiword_keys'],key=lambda x:(-x['source_message_frequency'],-x['occurrence_frequency'],x['source_key'])))}
 tables=collections.defaultdict(dict);audit={};db=ro(path('evidence'));train=lookup['train_rows'];usedheads=set()
 def add(table,key,value):
  old=tables[table].get(key);assert old is None or old==value,(table,key);tables[table][key]=value
 def form(ref,lang):
  f=data['dictionary_forms'][ref];assert f['complete'] and f['mode'] in (1,2);a,b=f['form_utf16'];assert a==0 and b==len(f['surface'].encode('utf-16-le'))//2
  add('forms',f['form_id'],(f['form_id'],lang,f['lexeme_id'],f['surface'],enc(f['form_utf16']),f['number'],f['mode'],enc(f['features']),f['headword'],f['pos'],int(f['source_safe']),int(f['target_safe']),int(f['complete']),enc(f['reasons']),digest(f)));return f['form_id']
 def term(t):
  assert t['eligible'] and t['explicit'] and not t['reasons'];add('terms',t['term_id'],(t['term_id'],t['sense_id'],t['reading'],int(t['eligible']),int(t['explicit']),enc(t['qualifiers']),enc(t['reasons']),digest(t)));return t['term_id']
 for key,v in sorted(lookup['rules'].items()):
  assert v['id']==digest(key) and key==enc([v['source_key'],v['focus_offset'],v['tokens']]);assert 2<=v['length']<=8 and len(v['tokens'])==v['length'] and 0<=v['focus_offset']<v['length'];assert v['winner_components']>=2
  add('rules',v['id'],(v['id'],v['source_key'],enc(v['tokens']),v['focus_offset'],v['length'],v['target'],v['ratio'],v['winner_components'],v['winner_weight'],digest(v),'conditional_research_only'))
  for hid,ids in sorted(v['admissible_head_rows'].items()):
   h=lookup['original_head_records'][hid];assert h['id']==hid and h['target_face']==v['target'];usedheads.add(hid);components={train[i]['component'] for i in ids};assert len(components)>=2;refs=set()
   for ident in ids:
    assert train[ident]['key']==v['source_key'];refs.update(train[ident]['valid_heads_by_face'][v['target']][hid])
   ar=digest([v['id'],hid]);audit[ar]={'rule_id':v['id'],'head_id':hid,'row_ids':sorted(ids),'components':sorted(components),'relation_refs':sorted(refs)};add('rule_heads',(v['id'],hid),(v['id'],hid,len(components),ar))
   for ref in sorted(refs):
    row=db.execute('select data from objects where id=?',(ref,)).fetchone();assert row;d=json.loads(row[0]);assert d['head']==hid and d['stratum']=='old_explicit_shared_link' and d['original_form_number_term_eligible'] and d['both_exact_form_roles_noun'] and not d['exact_focus_reasons'] and not d['original_envelope_reasons'];sf=form(d['source_form_ref'],'en');tf=form(d['target_form_ref'],'es');st=term(d['source_term']);tt=term(d['target_term']);assert d['source_term']['sense_id']==d['target_term']['sense_id'];assert [sf,tf,st,tt] in lookup['original_override_links'][hid];vals=(v['id'],hid,sf,tf,st,tt);add('links',vals,vals)
 for hid in sorted(usedheads):
  h=lookup['original_head_records'][hid];add('heads',hid,(hid,h['context_id'],h['source_key'],enc(h['source_context_token_text']),enc(h['source_focus_relative_tokens']),h['target_face'],enc(h['head_readings']),enc(h['source_pos']),int(h['fixed']),ranks.get(h['source_key'],10**9),digest(h),'conditional_source_name_only'))
 for source,family in sorted(control['source_families'].items()):add('known_families',source,(source,family))
 for source,roles in sorted(control['source_roles'].items()):add('source_roles',source,(source,enc(roles)))
 for source in sorted(function):add('function_words',source,(source,))
 metadata={'kind':'vipi.frozen-context-research','schema':'1','source':'en','target':'es','permission':'disabled_research_only','input_manifest_sha256':digest(p['inputs']),'policy_sha256':p['contract_sha256'],'normalization':'NFC+Unicode-casefold+whitespace-collapse; offsets never normalized','tokenizer_sha256':p['inputs']['tokenizer']['sha256'],'known_policy':'all nonempty knowledge IDs known, not concept alone; function classification unchanged','selector':'context-native-word-depth DESC,category,train_rank,cost DESC,focus_start,candidate_id; preserve original candidate enumeration','mask_policy':'external exact dictionary recognition plus protected/name ranges; never removed on empty/known/no-target; no automatic approvedOutputs','source_role':'exact current snapshot NOUN necessary, not sufficient; lowercase/content/single-token and every original guard required','backoff':'longest qualifying context first; no exception unigram; unavailable winner blocks shorter/alternate rescue','baseline':'addon only; requires unchanged original baseline/candidate inventory; not a complete replacement catalog','learned_family_order_json':enc(control['learned_family_order'])}
 for language in ['en','es']:
  dc=ro(path('dictionary_'+language));dm=dict(dc.execute('SELECT key,value FROM metadata'));dc.close();assert 'release_id' in dm and 'source_inventory_sha256' in dm
  metadata['dictionary_'+language+'_sha256']=p['inputs']['dictionary_'+language]['sha256'];metadata['dictionary_'+language+'_metadata_json']=enc(dm)
 for k,v in sorted(metadata.items()):add('metadata',k,(k,v))
 db.close();assert len(tables['rules'])==1157;assert sum(bool(x['admissible_head_rows']) for x in lookup['rules'].values())==1134
 return {t:[v for _,v in sorted(rows.items())] for t,rows in tables.items()},audit

def main():
 parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['measure','export']);args=parser.parse_args();assert socket.gethostname()=='fallsoft-production-20261106';start=time.monotonic();os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});os.nice(10);resource.setrlimit(resource.RLIMIT_AS,(1024**3,)*2);signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('120s')));signal.alarm(120);p=json.loads((R/'protocol.json').read_text());out=R/args.stage;out.mkdir(exist_ok=False);receipt={'complete':False,'protocol_sha256':sha(R/'protocol.json')}
 try:
  assert sha(__file__)==p['code_sha256'];assert sha(R/'CONTRACT.md')==p['contract_sha256'];assert shutil.disk_usage(R).free>8*1024**3+64*M
  for k,v in p['inputs'].items():assert sha(v['path'])==v['sha256'],k
  tables,audit=build_rows(p);logical=sum(len(enc(row).encode()) for rows in tables.values() for row in rows);rowhash=digest(tables);auditbytes=(enc({'input_hashes':p['inputs'],'support_edges':audit})+'\n').encode();assert len(auditbytes)<16*M
  receipt.update(rows={t:len(v) for t,v in tables.items()},logical_UTF8_row_bytes=logical,logical_rows_sha256=rowhash,audit_bytes=len(auditbytes),audit_sha256=hashlib.sha256(auditbytes).hexdigest())
  if args.stage=='export':
   # Both byte determinism and decoded row equality are checked under the same pinned SQLite runtime.
   hashes=[]
   for name in ['context.sqlite','determinism-check.sqlite']:
    path=out/name;db=sqlite3.connect(path);db.executescript(SCHEMA);db.execute('PRAGMA max_page_count=4096')
    for table in ['metadata','rules','heads','forms','terms','rule_heads','links','known_families','source_roles','function_words']:
     rows=tables.get(table,[])
     if rows:db.executemany('INSERT INTO '+table+' VALUES('+','.join('?' for _ in rows[0])+')',rows)
    db.commit();assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok';assert not db.execute('PRAGMA foreign_key_check').fetchall()
    for table,rows in tables.items():assert sorted(db.execute('SELECT * FROM '+table).fetchall(),key=enc)==sorted(rows,key=enc)
    db.close();assert path.stat().st_size<=16*M;hashes.append(sha(path))
   assert hashes[0]==hashes[1];(out/'determinism-check.sqlite').unlink();(out/'audit-manifest.json').write_bytes(auditbytes);receipt['pack_sha256']=hashes[0];receipt['pack_bytes']=(out/'context.sqlite').stat().st_size;receipt['byte_determinism_same_SQLite']=True
  receipt['complete']=True
 finally:
  receipt.update(seconds=time.monotonic()-start,VmHWM_bytes=int(next(x.split()[1] for x in pathlib.Path('/proc/self/status').read_text().splitlines() if x.startswith('VmHWM:')))*1024,sqlite_version=sqlite3.sqlite_version);(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
if __name__=='__main__':main()
