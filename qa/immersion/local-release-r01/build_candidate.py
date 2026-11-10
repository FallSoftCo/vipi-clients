"""Private, deterministic data-only candidates; no installation or runtime permission change."""
from pathlib import Path
import json,hashlib,copy
W=Path(__file__).parent;R=Path('/home/ai/Development/vipi-production-20261107');D=R/'data/immersion'
enc=lambda x:(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
sha=lambda b:hashlib.sha256(b).hexdigest()
review_path=W/'candidate-review-r01.json';review=json.loads(review_path.read_bytes());assert sha(review_path.read_bytes())=='0d5bdfdad71ce96d9b5d233f57db79ad64ca885c9b8cac7425505105f9e7c865'
O=W/'candidate-r01';O.mkdir(exist_ok=False)
kana={'high school':'こうこう','free time':'よか','country music':'カントリー','spare time':'よか','grocery store':'しょくりょうひんてん','ice cream':'アイスクリーム','fried chicken':'フライドチキン','computer science':'けいさんきかがく','social media':'ソーシャルメディア','rock music':'ロック','chocolate chip':'チョコチップ'}
omit={'last night':'Finite left-possessive/the rejection is not implemented.','next year':'Finite preceding-the rejection is not implemented.','only child':'Finite preceding-a/an requirement is not implemented.'}
positives={
'ice cream':'We shared some ice cream after dinner at home.',
'climate change':'We talked about climate change during lunch with friends.',
'radio station':'My friend works at the radio station near our house.',
'rap music':'We like listening to rap music together after work.',
'family member':'A family member is visiting our house for dinner today.',
'bad luck':'I had bad luck with the weather on our holiday.',
'mental health':'Getting enough rest is important for my mental health.',
'heart attack':'My father had a heart attack and went to hospital.',
'credit card':'I paid for our dinner with my credit card.',
'police officer':'My sister works as a police officer in our town.',
'cost of living':'The cost of living has increased in our town.',
 'this morning':'I went for a walk with my friend this morning.',
'boarding school':'My cousin lived at a boarding school for two years.',
'living room':'We put the new sofa in our living room.',
'electric car':'My neighbour bought an electric car to drive to work.',
'horror movie':'We watched a horror movie together at home last night.',
'common cold':'I stayed home from work because of the common cold.',
'sweet potato':'I made sweet potato casserole for our dinner today.',
'short story':'My friend wrote a short story about life at home.',
'fresh air':'We opened the window to let some fresh air inside.',
'high school':'I met my best friend when we were in high school.',
'free time':'I like to read books in my free time.',
'country music':'My family listens to country music while cooking at home.',
'spare time':'I enjoy drawing pictures in my spare time at home.',
'grocery store':'I bought some bread at the grocery store near home.',
'fried chicken':'We had fried chicken with vegetables for dinner at home.',
'computer science':'My sister studies computer science at the university near home.',
'social media':'I share pictures of my garden on social media.',
'rock music':'We listened to rock music on our way home.',
'chocolate chip':'I baked chocolate chip cookies for my family today.'}
contrasts={'heart attack':'You nearly gave me a heart attack with that loud noise!', 'fresh air':'Her honest advice was a breath of fresh air.', 'short story':'To make a long story short, we finally got home.', 'high school':'High School Musical is the title of her favourite film.', 'free time':'The parking meter gives us some free time before we must pay.', 'spare time':'My spare time machine is stored in the garage.', 'country music':'Country Music is the title printed on the book cover.', 'radio station':'The message says radio station.txt is missing from the folder.', 'sweet potato':'Sweet Potato is the nickname of my small dog.', 'horror movie':'The journey home was a horror movie from start to finish.', 'this morning':'This Morning is the television programme she watches.', 'common cold':'Common Cold is the name of the band on this poster.', 'credit card':'Please preserve the exact label `credit card` in the command.', 'climate change':'Please open climate_change.txt and leave the filename unchanged.', 'police officer':'Police Officer is the exact title of this computer game.', 'boarding school':'Boarding School is the exact title printed on the poster.'}
provenance=[];fixtures=[];reports={};inputs={str(review_path):sha(review_path.read_bytes())}
for lang,old,new,manifest_name in [('sw','006','007','starter-sw-catalog.json'),('ja','005','006','starter-catalog.json')]:
 parent=D/f'starter-en-{lang}-{old}.json';parent_bytes=parent.read_bytes();assert review['bindings'][str(parent)]==sha(parent_bytes);base=json.loads(parent_bytes);catalog=json.loads((D/manifest_name).read_bytes());assert catalog['sha256']==sha(parent_bytes)
 inputs[str(parent)]=sha(parent_bytes);inputs[str(D/manifest_name)]=sha((D/manifest_name).read_bytes());p=copy.deepcopy(base);old_entries=copy.deepcopy(base['entries']);n=0;rank=max(e['train_rank'] for e in old_entries)+1;omissions=[]
 for c in review['candidates']:
  if c['language']!=lang or not c['proposed_target']:continue
  source=c['source']
  if lang=='ja' and source in omit:omissions.append({'id':c['id'],'source':source,'reason':omit[source]});continue
  relation=c['chosen_retained_relation'];assert relation and relation['target_canonical_forms'] and relation['target_lexeme']['target_safe']==1
  concept='phrase:'+('leisure-time' if source in ['free time','spare time'] else source.replace(' ','-'))
  e={'id':'phrase-en-'+lang+'-'+source.replace(' ','-'),'source':source,'source_tokens':source.lower().split(),'target':c['proposed_target'],'category':'content','pos':relation['source_term']['sense_pos'],'concept_id':concept,'train_rank':rank+n}
  if lang=='ja':e.update(reading=c['proposed_reading'],reading_kana=kana[source]);assert e['reading'] and e['reading_kana']
  proof={'candidate_id':c['id'],'review_sha256':sha(review_path.read_bytes()),'relation':relation,'source_lexeme':c['all_evidence']['source']['source_lexeme'],'source_terms':c['all_evidence']['source']['source_terms'],'source_forms':c['all_evidence']['source']['source_forms'],'source_guards':c['all_evidence']['source']['source_guards'],'all_alternatives':c['all_evidence']['alternatives'],'license':c['all_evidence']['license'],'editorial_rationale':c['rationale'],'entry_without_hash':e.copy(),'reading_kana_provenance':'Manual kana transcription of retained romanized reading; independent review pending, not a new dictionary claim.' if lang=='ja' else 'Latin script target; no reading fields added.','runtime_guard':None,'source_only_acceptance':'test-only candidate permission, not production or semantic approval'}
  e['record_sha256']=sha(enc(proof));provenance.append(proof);p['entries'].append(e);n+=1
  for kind,text in [('positive',positives[source]),('contrast',contrasts.get(source,'Please keep `'+source+'` unchanged in the filename instruction.'))]:
   fixtures.append({'id':f'{lang}-{source.replace(" ","-")}-{kind}','pair':f'en-{lang}','source':text,'density_values':[0.25,0.75],'known_ids':[],'candidate_entry_id':e['id'],'kind':kind,'semantic_approval':False,'translation_calls_allowed':0})
 assert p['entries'][:len(old_entries)]==old_entries and [enc(e) for e in p['entries'][:len(old_entries)]]==[enc(e) for e in old_entries]
 p.update(version=f'starter-en-{lang}-{new}',activation='private_native_qualification_only',qualification_status='unreviewed_candidate_outputs_no_activation',local_phrase_parent_sha256=sha(parent_bytes),local_phrase_review_sha256=sha(review_path.read_bytes()),local_phrase_rank_policy='Append after all active train_rank values in retained nominated order; no output-based tuning.')
 b=enc(p);name=f'starter-en-{lang}-{new}.json';(O/name).write_bytes(b);m={'schema':'vipi-source-starter-manifest-1','file':name,'sha256':sha(b),'bytes':len(b),'version':p['version'],'entries':len(p['entries'])};(O/manifest_name).write_bytes(enc(m));reports[lang]={'parent_entries':len(old_entries),'added':n,'entries':len(p['entries']),'all_active_entries_exact':True,'manifest':m,'omitted':omissions}
# Shared adversarial controls, not additional vocabulary or semantic expectations.
for lang in ['ja','sw']:
 for ident,source in [('punctuation','We talked about ice. cream after dinner at home.'),('repetition','We shared ice cream and then ordered more ice cream.'),('literal','Please keep ice_cream.txt and `ice cream` exactly as written.'),('negation','I do not want ice cream with dinner tonight.')]:fixtures.append({'id':f'{lang}-shared-{ident}','pair':f'en-{lang}','source':source,'density_values':[0.25,0.75],'known_ids':[],'kind':'mechanism_or_semantic_contrast','semantic_approval':False,'translation_calls_allowed':0})
(O/'provenance.json').write_bytes(enc({'schema':'vipi-local-phrase-provenance-1','records':provenance}));(O/'fixtures.json').write_bytes(enc({'schema':'vipi-local-phrase-fixtures-1','cases':fixtures,'input_origin':'authored diagnostic sources; retained TRAIN witnesses are separate evidence','densities':[0.25,0.75],'no_target_text_in_native_inputs':True}));(O/'preservation.json').write_bytes(enc({'inputs':inputs,'pairs':reports,'active_record_comparison':'exact canonical JSON bytes per entry and order','runtime_changes':False,'pack_installed':False}));(O/'manifest.json').write_bytes(enc({x.name:sha(x.read_bytes()) for x in O.iterdir() if x.is_file()}));print(json.dumps(reports,indent=2));print('fixtures',len(fixtures))
