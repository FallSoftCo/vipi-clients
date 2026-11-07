#!/usr/bin/env python3
"""Reuse exact reviewed mappings in a separately scoped source-only experiment."""
import argparse,json,sqlite3,hashlib,datetime,itertools
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--data',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
R=a.output; R.mkdir(parents=True,exist_ok=False)
DATA=a.data
# Explicit candidate families, not blanket promotion of target-corroborated records.
SAFE={'en':{'today','tomorrow','yesterday','airport','restaurant','coffee','food','money','music','photo','weekend'},'es':{'aeropuerto','restaurante','dinero','música','foto','ayer','hoy'},'sw':{'kesho','jana','leo','uwanja wa ndege','mkahawa','pesa','muziki','chakula'}}
NOUN={'en':{'phone','email','book','door','bag','car','hotel','house','bus','train','school','student','meeting','lunch','dinner','breakfast','weekend','price'},'es':{'teléfono','correo electrónico','libro','puerta','bolsa','coche','hotel','casa','autobús','tren','escuela','estudiante','reunión','almuerzo','cena','desayuno','fin de semana','precio'},'sw':{'simu','barua pepe','kitabu','mlango','mfuko','gari','hoteli','nyumba','basi','treni','shule','mwanafunzi','mkutano','chakula cha mchana','chakula cha jioni','kifungua kinywa','mwisho wa wiki','bei'}}
BLOCKS={'food':['for thought'],'train':['of thought'],'school':['of fish'],'book':['of business'],'bus':['address','interface','controller','protocol'],'phone':['phoneme']}
def joined_parts(parts):
 # Original finite patterns concatenate character parts (Swahili prefixes are
 # inside a word). Combine each side before tokenizing; never invent spaces.
 focus=next(i for i,p in enumerate(parts) if 'focus' in p)
 out=[]
 for group in [parts[:focus], parts[focus:focus+1], parts[focus+1:]]:
  if not group:continue
  if 'focus' in group[0]:out.append(group[0]);continue
  choices=[p['slot'] if 'slot' in p else [p['literal']] for p in group]
  count=1
  for x in choices:count*=len(x)
  if count>4096:raise ValueError('Finite context exceeds bound')
  out.append({'choice':sorted(set(''.join(v) for v in itertools.product(*choices)))})
 return out
rules=[];records=[];pins=[];seen=set()
for s,t in [('en','es'),('en','sw'),('es','en'),('sw','en')]:
 path=DATA/(s+'-'+t+'.sqlite');pins.append({'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
 with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True) as db:
  for payload,evidence in db.execute('SELECT payload,evidence FROM mappings ORDER BY id'):
   r=json.loads(payload);ev=json.loads(evidence)
   if r['source']==r['target']:continue
   # These Latin-language records include a Cartesian capitalization matrix.
   # Select an actual lowercase target record; do not interpret casing as sense.
   if r['target'] != r['target'].lower():continue
   choices=[]
   if not r.get('source_lexical_unit',r.get('lexical_unit',False)):
    # Existing finite explicit source constructions retained with an additional right guard.
    parts=joined_parts(r['source_parts'])
    choices.append((parts,'any','adjunct','explicit_source_construction'))
   else:
    word=r['source'].lower()
    if r['id'].startswith('vipi-compound-unit'):
     choices.append(([{'focus':r['source']}],'lowercase','any','complete_compound'))
    if word in SAFE[s]:choices.append(([{'focus':r['source']}],'lowercase','any','source_unambiguous_family'))
    if word in NOUN[s]:
     choices.append(([{'focus':r['source']}],'noun_prefix','any','source_noun_context'))
     if s=='sw':choices.append(([{'focus':r['source']}],'any','possessive','source_possessive_context'))
    if ':chat_' in r['id']:
     choices.append(([{'focus':r['source']}],'clause','social','source_chat_clause'))
   for parts,left,right,scope in choices:
    key=json.dumps([s,t,parts,left,right,r['target']],sort_keys=True,ensure_ascii=False)
    if key in seen:continue
    seen.add(key)
    rules.append({'id':r['id']+':'+scope,'source':s,'target':t,'parts':parts,'replacement':r['target'],'left':left,'right':right,'kind':'phrase','blocked_following':BLOCKS.get(r['source'].lower(),[]),'record_sha256':r['record_sha256'],'meaning':r['meaning'],'source_only_assessment':'new candidate author scope; current both-side review does not itself approve this path'})
    records.append({'id':r['id'],'record_sha256':r['record_sha256'],'original_source_context':ev['record']['source_context'],'original_target_context':ev['record']['target_context'],'original_usage':ev['record']['usage']})
pack={'schema':'vipi-source-phrase-candidate-1','rules':rules,'release_ready':False,'independent_linguistic_acceptance':False,'source_files':pins}
raw=(json.dumps(pack,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode();(R/'pack.json').write_bytes(raw)
(R/'reused-record-evidence.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')
freeze={'pack_sha256':hashlib.sha256(raw).hexdigest(),'matcher_sha256':hashlib.sha256((Path(__file__).parent/'matcher.py').read_bytes()).hexdigest(),'freeze_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'rule_count':len(rules),'source_records':len({x['record_sha256'] for x in records}),'evidence_sha256':hashlib.sha256((R/'reused-record-evidence.json').read_bytes()).hexdigest(),'sampling':'Candidate build only; freeze before selecting/acquiring a new evaluation sample.','input_cases_inspected':'Not asserted by builder; identify evaluation-cohort exposure separately','release_ready':False}
(R/'freeze.json').write_text(json.dumps(freeze,indent=2)+'\n');print(freeze)
