"""Bounded existing-output/keyed dictionary audit; no annotation or selection."""
import pathlib,json,hashlib,sqlite3,subprocess,shlex,unicodedata
Q=pathlib.Path(__file__).resolve().parent;REPO=Q.parents[2];W=pathlib.Path('/home/ai/Development/investigations/vipi-target-informed-taskmaster-20261109-r01');sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();enc=lambda x:json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
review=json.loads((W/'author-review-r01.json').read_text());raw={r['id']:r for r in json.loads((W/'run-r02/output.json').read_text())['cases']};bad={}
for r in review['options']:
 for u in r['units']:
  if u['label']=='material_error':bad[(r['id'],enc(u['span']))]=u
bindings=json.loads((W/'causal-native-pack-bindings.json').read_text())
for n,v in bindings.items():assert sha(REPO/'data/immersion'/n)==v['sha256'],n
pack=sqlite3.connect('file:'+str(REPO/'data/immersion/en-es.sqlite')+'?mode=ro',uri=True);contexts=sqlite3.connect('file:'+str(REPO/'data/immersion/en-es-contexts.sqlite')+'?mode=ro',uri=True);catalog=json.loads((REPO/'data/immersion/catalog.json').read_text());references={x['original']:x['translation'] for x in catalog['references'] if x['pair']=='en-es'}
rows=[];keys={'en':set(),'es':set()}
for (ident,_),unit in sorted(bad.items()):
 r=raw[ident];s=unit['span'];text=r['original'];buf=text.encode('utf-16-le');a,b=s['source_utf16'];windows={}
 for left,right in r['source_native_sentences']:
  words=[(x,y) for x,y in r['source_native_words'] if left<=x and y<=right]
  for i,(x,_) in enumerate(words):
   for _,y in words[i:i+8]:
    if not x<=a<b<=y or y-x>256:continue
    key=buf[2*x:2*y].decode('utf-16-le')
    if any(c in key for c in '.!?。！？;；\r\n'):continue
    windows.setdefault(key,[]).append([x,y])
 hits=[]
 for key,scopes in sorted(windows.items()):
  for mid,payload,evidence in pack.execute('SELECT m.id,m.payload,m.evidence FROM source_inputs i JOIN mappings m ON m.id=i.mapping_id WHERE i.input=?',(key,)):
   hits.append({'input':key,'scopes':scopes,'id':mid,'payload':json.loads(payload),'evidence':json.loads(evidence)})
 sentences=[buf[2*x:2*y].decode('utf-16-le') for x,y in r['source_native_sentences']];ctx=[]
 for key in dict.fromkeys([text]+sentences):
  for mid,payload,evidence in contexts.execute('SELECT m.id,m.payload,m.evidence FROM context_inputs i JOIN mappings m ON m.id=i.mapping_id WHERE i.input=?',(key,)):ctx.append({'input':key,'id':mid,'payload':json.loads(payload),'evidence':json.loads(evidence)})
 edges=[json.loads(k[13:]) for k in r['lexical_diagnostics_aggregate_not_focus_labels'] if k.startswith('target_graph:') and '"kind":"edge"' in k];edges=[e for e in edges if e['source']==s['source_utf16'] and e['target']==s['target_utf16']]
 keys['en'].add(unicodedata.normalize('NFC',s['source']).casefold());keys['es'].add(unicodedata.normalize('NFC',s['target']).casefold())
 rows.append({'id':ident,'span':s,'source':text,'full_cached_target':r['translation'],'frozen_author_judgment':unit,'native_source_words':r['source_native_words'],'native_source_sentences':r['source_native_sentences'],'native_target_sentences':r['target_native_sentences'],'raw_occurrence_POS':'Computed in native source snapshot but not serialized; unavailable in retained evidence. Do not substitute dictionary POS.','source_masks':r['source_strict_masks'],'source_protections':r['source_overlap_protections'],'matching_graph_edges':edges,'primary_frame_source_hits':hits,'context_pack_exact_hits':ctx,'source_only_exact_references':[{'source':x,'target':references[x]} for x in dict.fromkeys([text]+sentences) if x in references],'window_reconstruction':'Uses retained whole-message native word/sentence ranges for exact substrings containing focus; no fresh tokenizer or claim of rerun fragment-token parity.'})
code='''import sqlite3,json
out={}
for lang,keys in KEYS.items():
 p='/srv/fallsoft/staging/vipi-context-key-expansion-20261109-r01/inputs/d-'+lang+'.sqlite';d=sqlite3.connect('file:'+p+'?mode=ro',uri=True);d.row_factory=sqlite3.Row
 forms=[dict(x) for x in d.execute('SELECT s.*,l.headword,l.pos,l.source_safe,l.target_safe,l.senses,l.source_url FROM surfaces s JOIN lexemes l ON l.id=s.lexeme WHERE s.normalized IN ('+','.join('?' for _ in keys)+') ORDER BY s.normalized,s.lexeme',keys)];ids=sorted({x['lexeme'] for x in forms});terms=[dict(x) for x in d.execute('SELECT t.*,s.explicit,s.label,s.source_url FROM terms t JOIN senses s ON s.id=t.sense WHERE t.lexeme IN ('+','.join('?' for _ in ids)+') ORDER BY t.lexeme,t.sense',ids)]
 out[lang]={'path':p,'forms':forms,'terms':terms,'guards':[dict(x) for x in d.execute('SELECT * FROM guards WHERE normalized IN ('+','.join('?' for _ in keys)+')',keys)],'schema':[list(x) for x in d.execute("SELECT name,sql FROM sqlite_master WHERE name IN ('surfaces','terms','senses','lexemes')")]}
print(json.dumps(out,ensure_ascii=False))
'''.replace('KEYS',repr({k:sorted(v) for k,v in keys.items()}))
a=subprocess.run(['ssh','-o','ConnectTimeout=15','fallsoft-production','python3 -B -c '+shlex.quote(code)],capture_output=True,text=True,timeout=30);(W/'causal-dictionary-query.json').write_text(json.dumps({'code':code,'returncode':a.returncode,'stderr':a.stderr,'fresh_full_dictionary_hash':False},indent=2)+'\n');assert a.returncode==0,a.stderr;dictionary=json.loads(a.stdout)
# Dictionary schema has compound form/term identities, not fabricated source-sense IDs.
for side in dictionary.values():
 for form in side['forms']:form['retained_record_sha256']=hashlib.sha256(enc(form).encode()).hexdigest()
 for term in side['terms']:term['compound_term_identity']=[term['lexeme'],term['sense'],term['reading']]
out={'rows':rows,'dictionary':dictionary,'dictionary_hashes_from_qualified_inputs':{'en':'5b16dafff9b2a27474792104bad11195ba8aff2236c134cf0265257b92727d68','es':'fcae976ecf9a8eb79c4ea0e4e214e19894db12c8eb21959270e1b9ce78ab1e8e'},'native_primary_pack_bindings':bindings,'no_new_inference':True,'no_predictions_or_policy_changes':True}
(W/'causal-inspection-r01.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'cases':len(rows),'pack_hits':[(r['id'],len(r['primary_frame_source_hits']),len(r['context_pack_exact_hits']),len(r['source_only_exact_references']),len(r['matching_graph_edges'])) for r in rows],'bytes':(W/'causal-inspection-r01.json').stat().st_size}))
