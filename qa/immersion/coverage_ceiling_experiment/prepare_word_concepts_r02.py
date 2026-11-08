#!/usr/bin/env python3
"""Reproduce the frozen TRAIN-selected r02 research lexicon from retained evidence."""
import argparse,json,hashlib,re
from pathlib import Path
parser=argparse.ArgumentParser()
parser.add_argument('--evidence-root',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
q=Path(__file__).resolve().parent; e=args.evidence_root
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
old=json.loads((q/'reviewed-word-lexicon-en-sw-r01.json').read_text()); draft=json.loads((q/'reviewed-word-additions-r02-draft.json').read_text()); freq=json.loads((e/'training-word-frequency1200-r02.json').read_text()); ranks={x['source']:x for x in freq['rows']}; audit=json.loads((e/'source-word-r02-draft-attestation-audit.json').read_text())['targets']
# These are complete ordinary number/orthographic forms of the same TRAIN-selected concept.
extra={'families':'family','schools':'school','houses':'house','rooms':'room','cities':'city','stores':'store','shops':'shop','farms':'farm','gardens':'garden','tree':'trees','lakes':'lake','beds':'bed','doctors':'doctor','nurses':'nurse','laws':'law','maths':'math','babies':'baby','sisters':'sister','sons':'son','daughters':'daughter','egg':'eggs','apples':'apple','minute':'minutes','reasons':'reason'}
# Avoid unsupported/over-specific target senses before any fresh outputs are selected.
reject={'hockey':'hokei spelling not attested in retained source; no invented spelling', 'baby':'mtoto mchanga specifically newborn/infant; review wider baby scope separately','babies':'same newborn/infant scope issue'}
entries=list(old['entries']); seen={x['source'] for x in entries}; omitted=[]
for category in ['content','function']:
 for source,target in draft[category].items():
  origin=source if source in ranks else extra.get(source)
  if source in seen:continue
  if source in reject or origin not in ranks:
   omitted.append({'source':source,'reason':reject.get(source,'Neither source nor explicitly paired concept is in TRAIN top1200')});continue
  provenance=audit.get(target,[])
  if source in ['son','sons']:
   components=[]
   for n,line in enumerate((e/'swahili-expansion-source/kaikki.org-dictionary-Swahili-20261107.jsonl').open(),1):
    x=json.loads(line)
    if x.get('word') in ['mwana','wana','kiume','wa'] and x.get('lang_code')=='sw':components.append(dict(raw_line=n,word=x['word'],pos=x.get('pos'),senses=x.get('senses',[]),url='https://en.wiktionary.org/wiki/'+x['word']+'#Swahili'))
   provenance=[dict(kind='authored_composition',scope='male child: mwana/wana + class1/2 genitive wa + kiume (male). Exact composed phrase is authored, not claimed as raw dictionary headword.',components=components,grammar_url='https://kiswahili.ku.edu/sites/kiswahili/files/documents/lessons/Lesson%201-10/all.pdf')]
  assert provenance,(source,target)
  pos='noun' if category=='content' else 'pron' if source in ['me','us','he','she','him'] else 'function'
  entries.append(dict(id='word-en-sw-'+source,source=source,target=target,category=category,pos=pos,train_rank=ranks[origin]['rank'],train_occurrences=ranks.get(source,{}).get('occurrences',0),concept=origin,selection_basis='TRAIN top1200 exact form' if source==origin else 'explicit complete form of TRAIN-selected '+origin,evidence=provenance,review='Reviewed ordinary lexical sense; homographs and idioms remain empirical error risks. Complete target, not a stem.'))
# Enforce a small local noun-context guard for NEW productive noun/verb homographs.
ambiguous={'school','schools','name','names','house','houses','place','places','store','stores','shop','shops','farm','farms','garden','gardens','snow','rain','water','nurse','nurses','milk','cake','cakes'}
for row in entries:
 if row['source'] not in seen and row['source'] in ambiguous: row['guard']='ordinary_noun_context'
 for item in row['evidence']:
  if 'word' in item:item.setdefault('url','https://en.wiktionary.org/wiki/'+item['word']+'#Swahili')
# Count aliases as one source concept, not as unique senses.
groups=[['i','me'],['we','us'],['he','she','him'],['yes','yeah'],['ok','okay'],['every','each'],['day','days'],['dog','dogs'],['cat','cats'],['year','years'],['thing','things'],['friend','friends'],['movie','movies'],['pet','pets'],['car','cars'],['child','children','kids'],['week','weeks'],['animal','animals'],['brother','brothers'],['sister','sisters'],['city','cities'],['mother','mom'],['father','dad'],['son','sons'],['daughter','daughters'],['hour','hours'],['month','months'],['holiday','holidays','vacation'],['boy','boys'],['girl','girls'],['horse','horses'],['song','songs'],['story','stories'],['language','languages'],['concert','concerts'],['math','maths'],['egg','eggs'],['minute','minutes']]
for w,o in extra.items():groups.append([w,o])
parent={x['source']:x['source'] for x in entries}
def root(x):
 while parent[x]!=x:x=parent[x]
 return x
for group in groups:
 group=[x for x in group if x in parent]
 for x in group[1:]:parent[root(x)]=root(group[0])
for x in entries:x['concept_id']=root(x['source'])
new=dict(old,schema='vipi-reviewed-source-word-lexicon-research-2',evaluation_cases_seen='Old development samples known; new r02 holdout not selected before this freeze',entries=entries,omitted_draft_entries=omitted,training_frequency_sha256=sha(e/'training-word-frequency1200-r02.json'),prior_lexicon_sha256=sha(q/'reviewed-word-lexicon-en-sw-r01.json'),addition_policy='No held-out sentence imported. TRAIN top1200 ordinary concepts plus explicit complete number/orthographic variants. Targets attested or explicitly authored composition with separate provenance.',summary=dict(entries=len(entries),distinct_concepts=len({x['concept_id'] for x in entries}),content_forms=sum(x['category']=='content' for x in entries),function_forms=sum(x['category']=='function' for x in entries),guarded_noun_forms=sum(bool(x.get('guard')) for x in entries)))
assert not args.output.exists()
write(args.output,new)
print(new['summary']);print('omitted',len(omitted)); print('new',[(x['source'],x['target']) for x in entries if x['source'] not in seen])
