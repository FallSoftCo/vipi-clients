import collections,hashlib,json,re
from pathlib import Path
Q=Path(__file__).resolve().parent;W=Path('/home/ai/Development/investigations/vipi-apertium-occurrence-roles-20261109-r01');B=Path('/home/ai/Development/investigations/vipi-bilingual-occurrence-roles-20261109-r01')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def key(e):return hashlib.sha256(json.dumps([e['language'],e['id'],e['text'],e['tokens']],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
def split_escaped(s,delimiter):
 parts=[];last=0;escape=False
 for i,ch in enumerate(s):
  if escape:escape=False;continue
  if ch=='\\':escape=True;continue
  if ch==delimiter:parts.append(s[last:i]);last=i+1
 parts.append(s[last:]);return parts
def unescape(s):return re.sub(r'\\(.)',r'\1',s)
def lexical_units(stream):
 units=[];begin=None;escape=False
 for i,ch in enumerate(stream):
  if escape:escape=False;continue
  if ch=='\\':escape=True;continue
  if ch=='^':assert begin is None;begin=i+1
  elif ch=='$' and begin is not None:
   fields=split_escaped(stream[begin:i],'/');assert len(fields)>=2;units.append({'surface':unescape(fields[0]),'readings':fields[1:],'raw':stream[begin-1:i+1]});begin=None
 assert begin is None;return units
def map_units(stream,text):
 cursor=0;lost=False;units=lexical_units(stream)
 for u in units:
  surface=u['surface'];start=text.find(surface,cursor)
  if lost or start<0:
   u['mapping']='unmatched_or_after_mapping_loss';u['codepoints']=None
   if text[cursor:].strip():lost=True
   continue
  if text[cursor:start].strip():
   u['mapping']='nonblank_gap_mapping_loss';u['codepoints']=None;lost=True;continue
  end=start+len(surface);u.update(mapping='exact_surface',codepoints=[start,end],utf16=[len(text[:z].encode('utf-16-le'))//2 for z in (start,end)]);cursor=end
 return units
def reading_role(reading,mapping):
 if reading.startswith('*'):return 'UNKNOWN'
 if len(split_escaped(reading,'+'))!=1:return 'UNASSESSABLE_JOINED_MORPHEMES'
 tags=re.findall(r'<([^>]+)>',reading)
 return mapping.get(tags[0],'UNMAPPED_TAG') if tags else 'UNMAPPED_TAG'
def token_evidence(token,analyzed,tagged,mapping):
 span=token['codepoints'];exact=[u for u in tagged if u['codepoints']==span];overlap=[u for u in tagged if u['codepoints'] and max(span[0],u['codepoints'][0])<min(span[1],u['codepoints'][1])];morph=[u for u in analyzed if u['codepoints']==span]
 result={'token':token,'tagged_units':exact if exact else overlap,'morphology_units':morph,'role':'UNASSESSABLE','reason':None}
 if len(exact)!=1:result['reason']='split_or_multiword_span' if overlap else 'no_exact_mapped_unit';return result
 if len(exact[0]['readings'])!=1:result['reason']='multiple_contextual_readings';return result
 role=reading_role(exact[0]['readings'][0],mapping)
 if role in ('UNKNOWN','UNASSESSABLE_JOINED_MORPHEMES','UNMAPPED_TAG'):result['reason']=role;return result
 result['role']=role;result['morphology_role_alternatives']=sorted({reading_role(r,mapping) for u in morph for r in u['readings']});return result
# Parser mechanism controls are structural only, unrelated to diagnostic target words.
assert split_escaped(r'a\/b/c','/')==[r'a\/b','c']
assert lexical_units(r'^x\$/x<n>$')[0]['surface']=='x$'
assert token_evidence({'codepoints':[0,3]},[],map_units('^one two/one two<np>$','one two'),{'np':'PROPN'})['reason']=='split_or_multiword_span'
plan=json.loads((Q/'protocol.json').read_text());packet=json.loads((B/'packet.json').read_text());assert sha(B/'packet.json')==plan['packet_sha256'];reviews={name:json.loads((B/(name+'-review-r01.json')).read_text()) for name in ('author','root')}
for name in reviews:assert sha(B/(name+'-review-r01.json'))==plan['reference_reviews'][name]
receipt=json.loads((W/'outputs/receipt.json').read_text());assert receipt['complete'];assert sha(W/'outputs/stages.jsonl')==receipt['outputs']['stages.jsonl']['sha256'];rows={r['endpoint_key']:r for r in map(json.loads,(W/'outputs/stages.jsonl').read_text().splitlines())};assert len(rows)==64
opennlp=json.loads((B/'joined-comparison.json').read_text());assert opennlp['inputs'][str(B/'packet.json')]==plan['packet_sha256'];counts=collections.defaultdict(collections.Counter);cases=[];errors=[];unassessable=[];endpoint_maps={}
for ci,c in enumerate(packet['cases']):
 case={'case_id':c['case_id'],'stratum':c['stratum'],'source':[],'target':[]}
 for side in ('source','target'):
  e=c['pair'][side];row=rows[key(e)];assert row['text_sha256']==hashlib.sha256(e['text'].encode()).hexdigest();analyzed=map_units(row['stages'][1]['output'],e['text']);tagged=map_units(row['stages'][2]['output'],e['text']);endpoint_maps[key(e)]={'morphology':analyzed,'contextual':tagged}
  for index in c[side+'_focus_indices']:
   ev=token_evidence(e['tokens'][index],analyzed,tagged,plan['tag_to_UPOS']);refs={name:next(t for t in review['cases'][ci][side] if t['index']==index) for name,review in reviews.items()};previous=next(t for t in opennlp['cases'][ci][side] if t['index']==index);entry={'index':index,'text':e['tokens'][index]['text'],'apertium':ev,'reviews':refs,'opennlp_role':previous['model_role'],'opennlp_score':previous['model_score']};case[side].append(entry)
   for name,ref in refs.items():
    metric=counts[(name,c['stratum'],side)];metric['all_focus_tokens']+=1;metric['assessable']+=ev['role']!='UNASSESSABLE';metric['correct']+=ev['role']==ref['role'];metric['reference_nouns']+=ref['role']=='NOUN';metric['false_noun_rejections']+=ref['role']=='NOUN' and ev['role'] not in ('NOUN','UNASSESSABLE');metric['unassessable_reference_nouns']+=ref['role']=='NOUN' and ev['role']=='UNASSESSABLE';metric['false_noun_acceptances']+=ref['role']!='NOUN' and ev['role']=='NOUN';metric['apertium_fixes_opennlp']+=ev['role']==ref['role'] and previous['model_role']!=ref['role'];metric['apertium_loses_opennlp_correct']+=ev['role'] not in (ref['role'],'UNASSESSABLE') and previous['model_role']==ref['role']
   if ev['role']=='UNASSESSABLE':unassessable.append({'case_id':c['case_id'],'side':side,**entry})
   elif any(ev['role']!=ref['role'] for ref in refs.values()):errors.append({'case_id':c['case_id'],'side':side,**entry})
 cases.append(case)
result={'inputs':{str(p):sha(p) for p in [B/'packet.json',B/'author-review-r01.json',B/'root-review-r01.json',B/'joined-comparison.json',W/'outputs/stages.jsonl',W/'outputs/receipt.json',Q/'protocol.json']},'cases':cases,'metrics':[{'reviewer':k[0],'stratum':k[1],'side':k[2],**v} for k,v in counts.items()],'errors':errors,'unassessable':unassessable,'endpoint_maps':endpoint_maps,'policy':'Exact single lexical-unit/token span mapping only; no relabeling, word-specific repair, translation gold or population accuracy. All morphology alternatives and chosen contextual readings retained.'}
p=W/'joined-comparison.json'
with p.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
print('sha',sha(p),'bytes',p.stat().st_size);print(json.dumps([x for x in result['metrics'] if x['reviewer']=='author']));print('errors',[(x['case_id'],x['side'],x['text'],x['apertium']['role'],x['reviews']['author']['role']) for x in errors]);print('unassessable',[(x['case_id'],x['side'],x['text'],x['apertium']['reason']) for x in unassessable])
