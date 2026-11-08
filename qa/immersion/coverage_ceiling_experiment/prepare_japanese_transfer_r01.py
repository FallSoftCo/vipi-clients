#!/usr/bin/env python3
"""Reproduce frozen Japanese research targets; preserves the observed r01 reading defect.

The exact frozen holdout results must remain reproducible. This builder deliberately
reproduces ICU kana-orthography conversion, including mataha for または; see the
separate semantic/reading decision. It is not a production language-pack compiler.
"""
import argparse
import json,hashlib,subprocess,unicodedata
from pathlib import Path
parser=argparse.ArgumentParser()
parser.add_argument('--source-dir',type=Path,default=Path(__file__).resolve().parent)
parser.add_argument('--evidence-dir',type=Path)
parser.add_argument('--dictionary',type=Path,required=True)
parser.add_argument('--output-dir',type=Path,required=True)
args=parser.parse_args();q=args.source_dir;e=args.evidence_dir or q/'primary-jmdict-selection-r01';o=args.output_dir
o.mkdir(parents=True,exist_ok=True)
assert subprocess.run(['uconv','-V'],text=True,capture_output=True,check=True).stdout.strip()=='uconv v2.1  ICU 74.2','Frozen romanizer version required.' 
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):
 assert not p.exists(),p
 p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert sha(args.dictionary)=='490d2fef9cd8dfcdfcd618863c827fe2efd52992b002fb502679d4e1b7fb039d'
assert sha(e/'selected-target-entry-evidence-r01.json')=='cfb68bed8b9389b05879b00dd6bea3bdb312a5c291dc69e1fdf4fef10ac1d0b5'
assert sha(e/'question-target-entry-evidence-r01.json')=='d40a57d3b340f01be5c8aac30f1b08f393494f3b021f73909e912a87eccc3d34'
draft=json.load(open(q/'japanese-transfer-targets-draft-r01.json'));source=json.load(open(q/'reviewed-word-lexicon-en-sw-r02.json'));rules=json.load(open(q/'source-question-rules-r02.json'))
assert set(draft['targets'])=={x['source'] for x in source['entries']}
raw=json.load(open(e/'selected-target-entry-evidence-r01.json'))['rows']+json.load(open(e/'question-target-entry-evidence-r01.json'));choices={}
for r in raw:
 for word in r['matched_targets']:choices.setdefault(word,[]).append(r)
explicit={'肉':'1463520','夜':'1536350','親':'1365040','町':'1603990','彼':'1483070','家':'1191730','はい':'1010080','きょうだい':'1249960','兄弟':'1249960','本':'1522150','また':'1524930','今':'1288850','私':'1311110','娘':'1531190','人':'1580640','朝':'1428280','たぶん':'1407980','たいてい':'1414580','年':'1468060','分':'1502840','しかし':'1505990','今日':'1579110','姉妹':'1579490','店':'1582120','ああ':'1565440','ここ':'1288810','夕食':'1542730','ペット':'1120990','毛':'1533820','車':'1323080','男の子':'1420010','女の子':'1344970','夫':'1496480','妻':'1294330','父':'1497610','母':'1514990','人々':'1580650','サッカー':'1056700','りんご':'1555480','パン':'1103090','ビール':'1104550','卵':'1549140','木':'1534520','月':'1255430','水':'1371260','山':'1302680','日':'1463770','湖':'1267280','猫':'1467640','先生':'1387990','朝食':'1428390','昼食':'1602330','どう':'1008910','どのくらい':'1009250','どんな':'1009330','いつ':'1188760','誰':'1416830','何':'1577100','なぜ':'1577120','どこ':'1577140'}
chosen={}
for word in sorted(set(x for x in draft['targets'].values() if x)|set(draft['question_targets'].values())):
 if word=='知っている':
  chosen[word]=dict(target=word,kana='しっている',reading_source='Explicit state form and te-form reading verified in NINJAL basic verb handbook. This complete form is not claimed to be a separate JMdict headword.',evidence=dict(kind='authored_complete_form_verified_primary',canonical='知る',canonical_reading='しる',te_form='しって',state_form=word,url='https://www2.ninjal.ac.jp/verbhandbook/headwords/%E7%9F%A5%E3%82%8B.html',scope='NINJAL explicitly distinguishes state-of-knowing shitteiru from coming-to-know shiru. No lesson prose copied.'))
  continue
 rs=choices[word]; row=next(x for x in rs if x['ent_seq']==explicit[word]) if word in explicit else rs[0]
 assert len(rs)==1 or word in explicit,(word,len(rs))
 spellings=[x['keb'] for x in row['kanji']]; readings=[r for r in row['readings'] if not r['restrictions'] or word in r['restrictions']]
 if word in [r['kana'] for r in row['readings']]:rd=next(r for r in row['readings'] if r['kana']==word)
 else:rd=readings[0]
 # Non-first senses are selected explicitly; do not treat the first homograph as truth.
 senses={'肉':[2],'また':[2,4],'時間':[2],'月':[2],'休み':[2]}.get(word,[1])
 ss=[s for s in row['senses'] if s['index'] in senses]
 assert ss and all(not s['kanji_restrictions'] or word in s['kanji_restrictions'] for s in ss)
 assert all(not s['reading_restrictions'] or rd['kana'] in s['reading_restrictions'] for s in ss)
 chosen[word]=dict(target=word,kana=rd['kana'],evidence=dict(kind='jmdict_exact_spelling_reading_sense',ent_seq=row['ent_seq'],selected_spelling=word,spelling_is_kana_entry=word not in spellings,all_kanji=spellings,selected_reading=rd,selected_senses=ss,dictionary_sha256=sha(args.dictionary),source_url='https://www.edrdg.org/pub/Nihongo/JMdict_e.gz',license='CC-BY-SA-4.0'))
words=sorted(chosen);roman=subprocess.run(['uconv','-x','Hiragana-Katakana; Katakana-Latin'],input='\n'.join(chosen[w]['kana'] for w in words)+'\n',text=True,capture_output=True,check=True).stdout.splitlines();assert len(roman)==len(words)
for word,reading in zip(words,roman):
 assert reading and all(c.isspace() or unicodedata.category(c)[0] in 'PM' or 'LATIN' in unicodedata.name(c,'') for c in reading),(word,reading)
 chosen[word]['reading']=reading
entries=[];unavailable=[]
for old in source['entries']:
 target=draft['targets'][old['source']]
 if target is None:unavailable.append(dict(source=old['source'],reason=draft['unavailable_reasons'][old['source']],category=old['category']));continue
 row={k:v for k,v in old.items() if k not in ['evidence','review','target','id']};row.update(id=old['id'].replace('en-sw','en-ja'),target=target,reading=chosen[target]['reading'],reading_kana=chosen[target]['kana'],evidence=chosen[target]['evidence'],review='Ordinary target meaning and exact reading selected before new Japanese holdout. Source English eligibility/ranking remains the frozen219 policy; no finite clauses transferred.')
 entries.append(row)
for section in ['single_words','units']:
 for word,row in rules[section].items():
  target=draft['question_targets'][word];row.update(target=target,reading=chosen[target]['reading'],reading_kana=chosen[target]['kana'],evidence=chosen[target]['evidence'])
rules['schema']='vipi-source-interrogative-context-japanese-transfer-1';rules['origin']='Exact source guards from frozen r02, Japanese target meanings/readings separately selected';rules['primary_sources']=[dict(url='https://www.edrdg.org/pub/Nihongo/JMdict_e.gz',scope='Exact Japanese spelling-reading-sense links retained per rule; unchanged English source conditions.')]
lex=dict(schema='vipi-source-word-japanese-transfer-1',production=False,training_only=True,source_policy_sha256=sha(q/'reviewed-word-lexicon-en-sw-r02.json'),target_selection_sha256=sha(q/'japanese-transfer-targets-draft-r01.json'),dictionary_sha256=sha(args.dictionary),dictionary_license='CC-BY-SA-4.0; EDRDG attribution/license/update requirements retained separately',attribution='These files are the property of the Electronic Dictionary Research and Development Group, and are used in conformance with the Group’s licence.',romanization='Pinned installed ICU uconv Hiragana-Katakana; Katakana-Latin on exact selected kana only, never automatic Any-Latin on Kanji. Source kana is also retained. Native speech binding remains separately unqualified.',entries=entries,unavailable=unavailable,summary=dict(source_forms=219,available_target_forms=len(entries),unavailable_target_forms=len(unavailable),content_forms=sum(x['category']=='content' for x in entries),function_forms=sum(x['category']=='function' for x in entries),mandatory_reading_present=sum(bool(x['reading']) for x in entries),distinct_target_strings=len({x['target'] for x in entries})))
write(o/'reviewed-word-lexicon-en-ja-transfer-r01.json',lex)
write(o/'source-question-rules-en-ja-transfer-r01.json',rules)
write(o/'reviewed-target-selection-r01.json',chosen)
old=json.loads((q/'reviewed-word-lexicon-en-sw-r01.json').read_text())
old_sources={row['source'] for row in old['entries']}
control=dict(lex,entries=[row for row in entries if row['source'] in old_sources],description='First100-source vocabulary research control transferred to Japanese; not current production runtime.')
# The frozen control inherited the full-lexicon summary. Preserve exact bytes and
# report actual counts separately, rather than silently changing the experiment.
write(o/'reviewed-word-control-en-ja-transfer-r01.json',control)
print(json.dumps(dict(lexicon=lex['summary'],actual_control_entries=len(control['entries'])),indent=2))
