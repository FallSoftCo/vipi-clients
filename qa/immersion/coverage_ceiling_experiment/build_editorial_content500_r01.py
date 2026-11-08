#!/usr/bin/env python3
"""Bind editorial ordinary faces to exact native evidence for bounded research.

Chosen target faces are authored, never shortest-string choices. Lexical overlap
only orders primary sense evidence for subsequent contextual review; it is not a
frequency estimate, semantic approval or runtime confidence score.
"""
import argparse,collections,csv,gzip,hashlib,json,re,unicodedata
from pathlib import Path
Q=Path(__file__).resolve().parent
BAD={'archaic','obsolete','dated','historical','rare','nonstandard','misspelling','error','uncommon'}
STOP=set('a an the to of in on for and or with from that which who one this as be is are was were by it its at into something someone have having being used relating pertaining especially usually person thing kind type act state'.split())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def norm(s):return unicodedata.normalize('NFKC',s).casefold()
def terms(s):
 ws=re.findall(r'[a-z]+',s.lower());return {w[:-1] if len(w)>4 and w.endswith('s') else w for w in ws if w not in STOP}
def score(gloss,query):return len(terms(' '.join(gloss))&terms(query))
def main():
 p=argparse.ArgumentParser();p.add_argument('--evidence-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();E=a.evidence_dir;M=E/'scaled-mechanism-cases-r01'
 paths={'preferences':M/'editorial-target-preferences500-r01.tsv','alternatives':M/'editorial-target-alternatives500-r01.json.gz','source_primary':E/'scaled-content-inventory-r01/raw-source-r02/selected-native-senses.json.gz','source_inventory':E/'scaled-content-inventory-r01/source-inventory.json','japanese':M/'editorial-japanese-primary-choices500-r01.json','target_primary':M/'editorial-target-primary500-r01/selected-native-targets.json.gz','target_supplement':M/'editorial-target-primary500-r02/selected-native-targets.json.gz','groups':Q/'role-content-candidate-r02.json'}
 data={k:read(v) for k,v in paths.items() if k!='preferences'};prefs=list(csv.DictReader(paths['preferences'].open(),delimiter='\t'));pref={}
 for r in prefs:pref[(r['source'],'adj' if r['source']=='human' and 'adjective' in r['intended_ordinary_sense'] else 'noun' if r['source']=='human' else None)]=r
 assert data['target_primary']['complete'] and data['target_supplement']['complete'];sources={r['source']:r for r in data['source_inventory']['rows']};source_en={x[0]:x for x in data['source_primary']['entries']};source_senses=collections.defaultdict(list)
 for r in data['source_primary']['senses']:source_senses[r[0]].append(r)
 en={};senses=collections.defaultdict(list);forms=collections.defaultdict(list)
 for d in [data['target_primary'],data['target_supplement']]:
  for r in d['entries']:en[r[0]]=r
  for r in d['senses']:senses[r[0]].append(r)
  for r in d['forms']:forms[r[0]].append(r)
 # Exact primary spelling/form membership, preserving lexical identity.
 face_index=collections.defaultdict(list)
 for entry_id,r in en.items():
  face_index[(r[1],r[2])].append((entry_id,None))
  for f in forms[entry_id]:
   tags=set(json.loads(f[3]));
   if tags&{'romanization','transliteration','canonical','alternative'}:continue
   if f[1] and f[1][0]!='-' and f[1][-1]!='-':face_index[(r[1],f[1])].append((entry_id,f))
 japanese={r['target']:r for r in data['japanese']['entries']};entries=[];unavailable=[];counts=collections.Counter()
 for row in data['alternatives']['rows']:
  word,pos=row['source'],row['source_pos'];pr=pref.get((word,pos)) or pref[(word,None)];intent=pr['intended_ordinary_sense'];query=word+' '+intent
  src=[]
  for le in sources[word]['content_lexemes']:
   if le['pos']!=pos or le['lexeme'] not in source_en:continue
   er=source_en[le['lexeme']]
   if er[2][0].isupper() or set(json.loads(er[5]))&BAD:continue
   for s in source_senses[le['lexeme']]:
    if set(json.loads(s[3]))&BAD or json.loads(s[4]) or json.loads(s[5]):continue
    gs=json.loads(s[2]);src.append((score(gs,query),le['headword']==word,le,s,gs))
  if not src:
   for lang in ['sw','ja','es']:unavailable.append({'source':word,'pos':pos,'language':lang,'reason':'source_primary_sense_unavailable'})
   continue
  src.sort(key=lambda x:(-x[0],not x[1],x[2]['lexeme'],x[3][1]));_,_,sl,ss,sg=src[0];source_entry=source_en[sl['lexeme']]
  source_form=next((f for f in sl['complete_surfaces'] if norm(f[0])==word),None)
  assert source_form,(word,sl)
  source_inflected=norm(sl['headword'])!=word and not set(json.loads(source_form[1]))&{'alternative'}
  concept=data['groups']['source_families'].get(word) or sl['headword'].casefold()
  for lang in ['sw','ja','es']:
   target=pr[lang].strip();reason=None;target_proof=None;reading=None;kana=None
   if not target:reason='editorial_target_or_sense_unresolved'
   elif norm(target)==norm(word):reason='unchanged_face'
   elif lang=='ja':
    jr=japanese.get(target)
    if not jr:reason='preferred_japanese_complete_primary_form_unavailable'
    elif jr['withhold_reason']:reason='japanese_calendar_month_scope_unresolved'
    else:
     allowed=[s for s in jr['compatible_senses'] if not set(s['misc'])&{'archaism','obsolete term','rare term'}]
     if not allowed:reason='modern_japanese_sense_unavailable'
     else:
      chosen=sorted(allowed,key=lambda s:(-score(s['gloss'],query),s['index']))[0]
      reading=jr['reading'];kana=jr['reading_kana'];target_proof={'kind':'JMdict_exact_spelling_reading_sense','entry_id':jr['jmdict_id'],'target':target,'reading_kana':kana,'selected_sense':chosen,'all_compatible_senses':allowed,'selected_reading':jr['selected_reading'],'dictionary_sha256':data['japanese']['dictionary_sha256'],'source_url':'https://www.edrdg.org/pub/Nihongo/JMdict_e.gz','license':'CC-BY-SA-4.0'}
   else:
    opts=[]
    for lex,form in face_index.get((lang,target),[]):
     er=en[lex]
     if set(json.loads(er[5]))&BAD or er[2].startswith('-') or er[2].endswith('-'):continue
     for s in senses[lex]:
      if set(json.loads(s[3]))&BAD or json.loads(s[4]) or json.loads(s[5]):continue
      gs=json.loads(s[2]);opts.append((score(gs,query),er[4]==pos,lex,form,s,gs))
    if not opts:reason='preferred_native_form_or_modern_sense_unavailable'
    else:
     opts.sort(key=lambda x:(-x[0],not x[1],x[2],x[4][1]));_,_,lex,form,se,gl=opts[0];er=en[lex]
     if source_inflected and 'plural' in set(json.loads(source_form[1])) and (not form or 'plural' not in set(json.loads(form[3]))):reason='source_plural_target_number_realization_unqualified'
     else:target_proof={'kind':'wiktionary_exact_native_entry_form_sense','entry':er,'selected_sense':se,'glosses':gl,'selected_form':form,'all_modern_senses':[s for s in senses[lex] if not set(json.loads(s[3]))&BAD],'source_url':er[6],'license':'CC-BY-SA-4.0'}
   if reason:unavailable.append({'source':word,'pos':pos,'language':lang,'preferred_target':target,'reason':reason});counts[(lang,reason)]+=1;continue
   evidence={'editorial_intended_sense':intent,'source_entry':source_entry,'source_selected_sense':ss,'source_glosses':sg,'source_attested_form':source_form,'source_common_alternatives':[{k:g[k] for k in ['source_entry_id','sense_id','sense_label','language_breadth']} for g in row['sense_groups']],'target':target_proof,'editorial_preference_source_sha256':sha(paths['preferences']),'sense_evidence_ordering':'Token overlap with the authored sense only ranks exact primary evidence for review. No frequency, semantic certainty or global all-senses-agreement claim.'}
   entries.append({'id':f'editorial500-r01-en-{lang}-{word}-{pos}','source':word,'pos':pos,'source_pos':pos,'language':lang,'target':target,'reading':reading,'reading_kana':kana,'category':'content','concept_id':concept,'train_rank':row['rank'],'source_form_kind':'attested_inflected' if source_inflected else 'canonical_or_alternative','source_kind':'editorial_primary','evidence':evidence,'semantic_review_status':'unqualified_candidate','target_dictionary_form_caveat':pos=='adj','contextual_alternative_risk':'alternative' in intent or 'versus' in intent})
   counts[(lang,'candidate')]+=1
 out={'schema':'vipi-editorial-primary-content500-research-1','production':False,'semantic_approval':False,'source_pos_pairs':500,'source_languages':['en'],'target_languages':['sw','ja','es'],'input_hashes':{k:sha(v) for k,v in paths.items()},'builder_sha256':sha(Path(__file__)),'selection':'Authored ordinary target preferences with exact primary entry/form/reading proof. Low-overlap primary sense ordering and contextual alternatives remain explicit review risks. No word-length ranking, all-sense consensus, or prior-test-selection admission.','entries':entries,'unavailable':unavailable,'source_families':data['groups']['source_families'],'learned_family_order':data['groups']['learned_family_order'],'capitalized_homographs':sorted({r[2].casefold() for r in source_en.values() if r[2][0].isupper() and r[2].casefold() in sources}),'summary':{'|'.join(k):v for k,v in counts.items()}}
 assert not a.output.exists();a.output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps(out['summary']));print('sha256',sha(a.output))
if __name__=='__main__':main()
