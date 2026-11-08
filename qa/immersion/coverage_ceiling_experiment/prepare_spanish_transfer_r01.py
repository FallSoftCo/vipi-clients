#!/usr/bin/env python3
"""Reproduce frozen Spanish transfer assets from retained primary lexical evidence."""
import copy
import hashlib
import json
from pathlib import Path
from urllib.parse import quote

import argparse

Q = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
OUT = args.output
OUT.mkdir(parents=True, exist_ok=False)
R = Q / 'primary-spanish-selection-r01'
draft = json.loads((R/'targets-draft.json').read_text())
assert hashlib.sha256((Q/'reviewed-word-lexicon-en-sw-r02.json').read_bytes()).hexdigest() == draft['source_sha256']
files = {}
for original in json.loads((R/'manifest.json').read_text())['files']:
    item = dict(original, local=str(R/original['path']))
    assert item['state'] == 'downloaded'
    assert hashlib.sha256(Path(item['local']).read_bytes()).hexdigest() == item['sha256']
    files[item['word']] = item

def records(word):
    return [json.loads(x) for x in Path(files[word]['local']).read_text().splitlines()]

def proof(word, ri, si):
    obj=records(word)[ri];sense=obj['senses'][si];f=files[word]
    digest=hashlib.sha256(json.dumps(sense,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    return {'exact_spelling':word,'part_of_speech':obj['pos'],
      'source_record_id':f"{f['sha256']}:record:{ri}",
      'sense_ids':[f"record:{ri}:sense:{si}:sha256:{digest}"],
      'sense_index':si,'glosses':sense.get('glosses',[]),'tags':sense.get('tags',[]),
      'form_of':sense.get('form_of',[]),'alt_of':sense.get('alt_of',[]),
      'source_sha256':f['sha256'],'license':'CC-BY-SA-4.0',
      'url':'https://en.wiktionary.org/wiki/'+quote(word,safe='')+'#Spanish',
      'machine_url':f['url']}

pos_override={'yes':'particle','yeah':'particle','because':'conj','online':'adj','oh':'intj','ok':'intj','okay':'intj','each':'det'}
scope_override={'weather':(0,3),'teacher':(1,1),'especially':(0,1),'movie':(0,1),'story':(0,4),'cake':(0,1),'meat':(0,1),'store':(0,1),'shop':(0,1)}
lemma_override={'película':(0,1),'tienda':(0,1),'historia':(0,4),'pastel':(0,1)}
entries=[]
for e in draft['entries']:
    word=e['target'];objs=records(word)
    pos=pos_override.get(e['source'],e['pos'])
    ri,si=scope_override.get(e['source'],(next(i for i,o in enumerate(objs) if o['pos']==pos),0))
    selected=proof(word,ri,si);evidence=[selected]
    sense=objs[ri]['senses'][si]
    for ref in sense.get('form_of',[]) + sense.get('alt_of',[]):
        base=ref['word']
        assert base in files,(word,base,'missing primary lemma')
        bs=records(base)
        bri,bsi=lemma_override.get(base,(next(i for i,o in enumerate(bs) if o['pos']==pos),0))
        evidence.append(proof(base,bri,bsi))
    entry=copy.deepcopy(e)
    entry['evidence']=evidence
    entry['review']='Root selected the ordinary source concept and the exact Spanish written form/sense from retained primary records before seeing the new target holdout. This attests the lexical unit, not correctness in every sentence; original English grammar remains and contextual/infinitive/register errors remain evaluation outcomes.'
    entry['unchanged_latin_face']=entry['source'].casefold()==entry['target'].casefold()
    if e['source'] in ('ok','okay'):
        entry['target_register']='The selected vale interjection is marked Spain in the retained dictionary. Regional suitability is explicit, not claimed universal.'
    entries.append(entry)

words={
 'schema':'vipi-reviewed-source-target-transfer-research-1',
 'production':False,'training_only':True,'new_target_holdout_seen':False,
 'source_policy_sha256':draft['source_sha256'],
 'source_guards_unchanged':True,'target_language':'es',
 'provenance':'English Wiktionary via Kaikki, per-word JSONL fetched November8,2026; exact record/sense content hashes retained. Record IDs here are content-addressed local IDs, not claimed publisher IDs.',
 'entries':entries,'unavailable':draft['unavailable'],
 'limitations':['Dictionary attestation is not context disambiguation or bilingual human validation.','Infinitive verbs preserve lexical meaning but can give a mixed finite English clause a minor target grammar mismatch.','No new English source guards or fifteen-clause rules are introduced.','Identical normalized Latin faces must remain unchanged and earn no immersion coverage credit.','Exclusions are target-transfer limits, not a claim that those English words can never be immersed.'],
 'summary':{'attested_source_forms':len(entries),'unavailable_source_forms':len(draft['unavailable']),'identical_faces':sum(e['unchanged_latin_face'] for e in entries)}
}
source_questions=json.loads((Q/'source-question-rules-r02.json').read_text())
questions=copy.deepcopy(source_questions)
questions.update(schema='vipi-source-question-target-transfer-research-1',target_language='es',source_question_sha256=hashlib.sha256((Q/'source-question-rules-r02.json').read_bytes()).hexdigest(),new_target_holdout_seen=False)
single={'what':('qué',2,0),'where':('dónde',0,0),'when':('cuándo',0,0),'why':('por qué',0,0),'who':('quién',0,0),'how':('cómo',0,0)}
for source,(target,ri,si) in single.items():
    questions['single_words'][source].update(target=target,reading=None,evidence=[proof(target,ri,si)])
units={'what kind':('qué tipo','tipo'),'what kinds':('qué tipos','tipo'),'what type':('qué tipo','tipo'),'what types':('qué tipos','tipo'),'what sort':('qué clase','clase'),'how long':('cuánto tiempo','tiempo')}
for source,(target,noun) in units.items():
    first='cuánto' if source=='how long' else 'qué'
    ri=1 if first=='cuánto' else 0
    nr=next(i for i,o in enumerate(records(noun)) if o['pos']=='noun')
    selected_noun=proof(noun,nr,4 if noun=='clase' else 0)
    unit_evidence=[proof(first,ri,0),selected_noun]
    if source in ('what kinds','what types'):
        unit_evidence.append(proof('tipos',1,0))
    questions['units'][source].update(target=target,reading=None,evidence=unit_evidence,
      construction='Finite authored interrogative noun phrase; source following-auxiliary/of constraint is unchanged. Spanish nominal agreement is internal to the target unit; the rest of the message remains original.')
questions['primary_sources']=[
 {'url':'https://cvc.cervantes.es/Ensenanza/biblioteca_ele/plan_curricular/niveles/02_gramatica_inventario_a1-a2.htm','scope':'Search-indexed primary curriculum corroborates interrogative roles. Current direct page redirects to maintenance; do not claim a complete page inspection or depend solely on it.'},
 {'url':'https://www.rae.es/gtg/docs/GTG_tablas_web.pdf','scope':'Interrogative cuánto, including temporal cuánto tiempo; verification only.'}]
questions['limitations'] += ['English question selection is unchanged; qué/cual and quién/quiénes context/number distinctions remain possible minor or material outcomes.','Unit plural tipo(s) is authored regular agreement; preserve number and do not reuse singular target for plural source.']

for name,obj in [('reviewed-word-lexicon-en-es-transfer-r01.json',words),('source-question-rules-en-es-transfer-r01.json',questions)]:
    p=OUT/name
    assert not p.exists(),'Frozen target already exists; inspect before creating a new revision'
    p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
freeze={'production':False,'new_target_holdout_seen':False,'paired_japanese_source_packet_opened':False,
 'scope':'Spanish target choices, primary senses and exclusions frozen before seeing new paired source sample; source policy unchanged.',
 'files':[{ 'path':n,'sha256':hashlib.sha256((OUT/n).read_bytes()).hexdigest()} for n in ['reviewed-word-lexicon-en-es-transfer-r01.json','source-question-rules-en-es-transfer-r01.json']],
 'source_policy_sha256':draft['source_sha256'],'primary_input_bytes':sum(x['bytes'] for x in files.values()),'primary_input_records':len(files),
 'attestation_review':'Root read all196 compact lexical attestations before freezing; selected exact primary noun senses and linked forms. Not an independent human semantic audit.',
 'summary':words['summary']}
(OUT/'spanish-transfer-target-freeze-r01.json').write_text(json.dumps(freeze,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(freeze,ensure_ascii=False))

control_path = Q / 'reviewed-word-lexicon-en-sw-r01.json'
control_sources = {e['source'] for e in json.loads(control_path.read_text())['entries']}
control = copy.deepcopy(words)
control['entries'] = [e for e in words['entries'] if e['source'] in control_sources]
control['control_source_sha256'] = hashlib.sha256(control_path.read_bytes()).hexdigest()
control['control_description'] = 'First100 English source forms, using this frozen Spanish target/exclusion policy. Not the deployed runtime.'
(OUT/'reviewed-word-lexicon-en-es-control-r01.json').write_text(json.dumps(control,ensure_ascii=False,indent=2)+'\n')
expected = {
 'reviewed-word-lexicon-en-es-transfer-r01.json':'d8d47bf4668a0e8f5fcd14589251c980ef7e71719d9de33cabf6b36c882e947e',
 'source-question-rules-en-es-transfer-r01.json':'615f7a674198f9c1631d66ea513d701673bd5c908e172afe1a69245454e37b63',
 'reviewed-word-lexicon-en-es-control-r01.json':'b39fbd55a7d9decaa6acdb455610b3e2e6c4e6eb31f3a69999bc9f1c6e036efc',
 'spanish-transfer-target-freeze-r01.json':'3a878665318b4e8a7c46be36e1876235ac042b326a5a6dc32b2dcca6e6764177'
}
for name, digest in expected.items():
    actual = hashlib.sha256((OUT/name).read_bytes()).hexdigest()
    assert actual == digest, (name, actual, digest)
print(json.dumps({'reproduced':expected,'inputs':len(files),'primary_input_bytes':sum(x['bytes'] for x in files.values())},indent=2))
