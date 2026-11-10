"""Data-only correction. Reuses current guard semantics; never edits runtime or fixtures."""
from pathlib import Path
import json,hashlib,copy,re
W=Path(__file__).parent;I=W/'candidate-r01';O=W/'candidate-r02';enc=lambda d:(json.dumps(d,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode();sha=lambda b:hashlib.sha256(b).hexdigest()
assert sha((I/'manifest.json').read_bytes())=='2b15ff491db65ad8698fb03f91bfc14b640d288d2b80257956b7910bab85dc17'
for n,h in json.loads((I/'manifest.json').read_bytes()).items():assert sha((I/n).read_bytes())==h
peer=W/'peer-meaning-review-r01.json';assert sha(peer.read_bytes())=='8b318fa175967f477b77140c5ca1b341e12aa6159c4d8c2a7ebdae0d72133946'
O.mkdir(exist_ok=False);fixtures=json.loads((I/'fixtures.json').read_bytes());proofs=json.loads((I/'provenance.json').read_bytes())['records'];pmap={sha(enc(p)):p for p in proofs};outproofs=[];report={'parent_manifest_sha256':sha((I/'manifest.json').read_bytes()),'peer_review_sha256':sha(peer.read_bytes()),'native_validation_pending':True,'guard_assessment':[],'pairs':{}}
# Only the existing ordinary_noun_context branch is evaluated here; this is not native parity evidence.
def noun_gate(source,phrase,sets):
 tokens=list(re.finditer(r"[A-Za-z]+(?:['’][A-Za-z]+)*",source));keys=[m.group().lower().replace('’',"'") for m in tokens];wanted=phrase.split();answers=[]
 for i in range(len(tokens)-len(wanted)+1):
  j=i+len(wanted)
  if keys[i:j]!=wanted:continue
  start,end=tokens[i].start(),tokens[j-1].end();prefix=source[:start].strip().rstrip('"\'“”‘’');initial=not prefix or prefix[-1] in '.!?';left=keys[i-1] if i and not source[tokens[i-1].end():start].strip() else '';right=keys[j] if j<len(tokens) else '';allowed=left in set(sets['determiners']+sets['prepositions']+sets['object_verbs']) or (initial and right in sets['copulas']);answers.append({'span':[start,end],'left':left,'right':right,'sentence_initial':initial,'ordinary_noun_context_allows':allowed})
 return answers
holds={'sw':['police officer','this morning','boarding school','common cold','sweet potato'],'ja':['country music']};leisure=['free time','spare time']
for lang,old,new,active_n,cat in [('sw','007','008',222,'starter-sw-catalog.json'),('ja','006','007',189,'starter-catalog.json')]:
 oldp=json.loads((I/f'starter-en-{lang}-{old}.json').read_bytes());p=copy.deepcopy(oldp);removed=[];updated=[];entries=[]
 for e in p['entries']:
  if e['source'] in holds[lang] or (lang=='ja' and e['source'] in leisure):
   assert e['id'].startswith('phrase-en-');removed.append({'id':e['id'],'source':e['source'],'reason':'leisure sense/constituent mismatch' if e['source'] in leisure else 'existing noun guard admits sentence-initial title followed by is; needs separate source-context support'});continue
  if e['id']=='phrase-en-ja-high-school':
   previous=e['record_sha256'];e['guard']='ordinary_noun_context';proof=copy.deepcopy(pmap[previous]);proof['parent_record_sha256']=previous;proof['correction_review_sha256']=sha(peer.read_bytes());proof['runtime_guard']='ordinary_noun_context';proof['editorial_rationale']+=' Existing guard permits in high school and withholds initial High School Musical (right token musical, not copula). Other proper titles may remain ambiguous; no universal name protection claim.';proof['entry_without_hash']={k:v for k,v in e.items() if k!='record_sha256'};e['record_sha256']=sha(enc(proof));outproofs.append(proof);updated.append({'id':e['id'],'change':'add ordinary_noun_context','old_record_sha256':previous,'new_record_sha256':e['record_sha256']})
  elif e['id'].startswith('phrase-en-'):outproofs.append(pmap[e['record_sha256']])
  entries.append(e)
 for phrase in holds[lang]+(['high school'] if lang=='ja' else []):
  matching=[x for x in fixtures['cases'] if x.get('candidate_entry_id')==f'phrase-en-{lang}-'+phrase.replace(' ','-')]
  report['guard_assessment'].append({'language':lang,'phrase':phrase,'cases':[{'id':x['id'],'source':x['source'],'assessment':noun_gate(x['source'],phrase,oldp['source_context_sets'])} for x in matching]})
 p['entries']=entries;assert entries[:active_n]==oldp['entries'][:active_n];p.update(version=f'starter-en-{lang}-{new}',local_phrase_correction_parent_sha256=sha((I/f'starter-en-{lang}-{old}.json').read_bytes()),local_phrase_correction_review_sha256=sha(peer.read_bytes()),qualification_status='corrected_private_candidate_pending_native_and_semantic_review');b=enc(p);filename=f'starter-en-{lang}-{new}.json';(O/filename).write_bytes(b);catalog={'schema':'vipi-source-starter-manifest-1','file':filename,'sha256':sha(b),'bytes':len(b),'version':p['version'],'entries':len(entries)};(O/cat).write_bytes(enc(catalog));report['pairs'][lang]={'entries':len(entries),'active_unchanged':active_n,'new':len(entries)-active_n,'removed':removed,'updated':updated,'catalog':catalog}
(O/'fixtures.json').write_bytes((I/'fixtures.json').read_bytes());assert sha((O/'fixtures.json').read_bytes())=='ef4c9940029c94a42491d096dc90a3b8b4b8599624f380ff13a9551d248cb1b9'
(O/'provenance.json').write_bytes(enc({'schema':'vipi-local-phrase-provenance-1','records':outproofs}));(O/'correction.json').write_bytes(enc(report));(O/'manifest.json').write_bytes(enc({p.name:sha(p.read_bytes()) for p in O.iterdir() if p.is_file()}));print(json.dumps(report['pairs'],indent=2));print('manifest',sha((O/'manifest.json').read_bytes()))
