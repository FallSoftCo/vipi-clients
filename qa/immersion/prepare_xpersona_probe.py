#!/usr/bin/env python3
"""Development probes from human-adapted validation; official tests stay reserved."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from acquire_xpersona import REVISION,LANGUAGES as SOURCE_LANGUAGES
from conversation_corpus import LANGUAGES,key,sha_file,write_json
from conversation_priority import tokenize
from prepare_sms_probe import first_word


def hash_text(text):return hashlib.sha256(text.encode()).hexdigest()


def utterances(dialogue):
    pairs=dialogue['dialogue']
    if not isinstance(pairs,list) or not 1<=len(pairs)<=1000:raise ValueError('Unexpected dialogue shape')
    for turn,pair in enumerate(pairs):
        if not isinstance(pair,list) or len(pair)!=2:raise ValueError('Expected two-speaker turn pair')
        for speaker,text in enumerate(pair):
            if not isinstance(text,str) or len(text)>10000:raise ValueError('Unexpected utterance')
            if text.startswith('__') and text.endswith('__'):continue
            if text.strip():yield 2*turn+speaker,text


def rank(language,index):return hash_text(f'vipi-xpersona-dialogue-1:{language}:{index}')


def choose(language,dialogues,training_texts,count):
    groups={};counts=Counter();candidates=[]
    for index,dialogue in enumerate(dialogues):
        rows=list(utterances(dialogue));counts['validation_utterances']+=len(rows)
        # Retain one representative of identical full utterance inventories,
        # including reversed speaker views. This is not participant separation.
        family=tuple(sorted({key(text) for _,text in rows}))
        if family in groups:counts['duplicate_full_dialogue_views']+=1;continue
        groups[family]=index;eligible=[]
        for turn,text in rows:
            if not 1<=len(text)<=280:counts['excluded_length']+=1;continue
            if key(text) in training_texts:counts['excluded_training_duplicate']+=1;continue
            focus=first_word(text,language)
            if focus is None:counts['excluded_no_word']+=1;continue
            digest=hash_text(f'vipi-xpersona-turn-1:{language}:{index}:{turn}:{text}')
            eligible.append((digest,index,turn,text,focus))
        if eligible:candidates.append(min(eligible))
    counts['eligible_dialogue_views']=len(candidates)
    selected=[];seen=set()
    for row in sorted(candidates,key=lambda row:(rank(language,row[1]),row[1])):
        if key(row[3]) in seen:counts['excluded_selected_duplicate']+=1;continue
        selected.append(row);seen.add(key(row[3]))
        if len(selected)==count:break
    if len(selected)!=count:raise ValueError(f'Insufficient distinct {language} validation dialogues: {len(selected)} / {count}')
    return selected,dict(counts)


def main(a):
    if not 1<=a.per_language<=300 or len(set(a.languages))!=len(a.languages):raise ValueError('Bounded unique languages required')
    if not a.apple_run_id.isascii() or not a.apple_run_id.isdigit() or len(a.apple_run_id)!=3:raise ValueError('Three-digit run ID required')
    receipt_path=a.source/'acquisition.json';receipt=json.loads(receipt_path.read_text())
    if receipt['revision']!=REVISION:raise ValueError('Wrong source revision')
    files={row['path']:row for row in receipt['files']};prefixes={v:k for k,v in SOURCE_LANGUAGES.items()}
    def read(name):
        path=a.source/name
        if path.stat().st_size!=files[name]['bytes'] or sha_file(path)!=files[name]['sha256']:raise ValueError('Changed acquired source')
        value=json.loads(path.read_text())
        if not isinstance(value,list):raise ValueError('Expected dialogue list')
        return value
    a.output.mkdir(parents=True,exist_ok=False);cases=[];samples=[];reports=[]
    codes=list(LANGUAGES.values())
    for language in a.languages:
        prefix=prefixes[language]
        train_name=f'dataset/{prefix}_persona_'+('train' if prefix=='En' else 'train_corrected')+'.json'
        valid_name=f'dataset/{prefix}_persona_'+('valid' if prefix=='En' else 'split_valid_human_annotated')+'.json'
        training=read(train_name);training_texts=set();frequency=Counter();raw_turns=0
        for dialogue in training:
            for _,text in utterances(dialogue):
                raw_turns+=1;normalized=key(text)
                if normalized in training_texts:continue
                training_texts.add(normalized);frequency.update(tokenize(text,language))
        train_count=len(training);del training
        validation=read(valid_name);selected,selection=choose(language,validation,training_texts,a.per_language)
        for digest,index,turn,text,(start,end,word) in selected:
            identifier='xpv-'+digest[:24];cases.append({'id':identifier,'text':{language:text}})
            for target in codes:
                if target!=language:samples.append({'case':identifier,'source':language,'target':target,'original':text,
                    'start':start,'end':end,'source_word':word,'evaluation_scope':'XPersona human-adapted validation development probe; no translation gold'})
        reports.append({'language':language,'training_dialogue_views':train_count,'training_utterances':raw_turns,
            'distinct_training_utterances':len(training_texts),'validation_dialogue_views':len(validation),
            'selection_counts':selection,'selected_views':[{'index':r[1],'turn':r[2]} for r in selected],
            'distinct_training_turn_word_frequencies':frequency.most_common(100),
            'frequency_limit':'Distinct normalized training turns only; includes grammar/names; translated data, not population chat frequency',
            'train_sha256':files[train_name]['sha256'],'validation_sha256':files[valid_name]['sha256']})
    pairs=len(a.languages)*9
    attribution={'source':'https://github.com/HLTCHKUST/Xpersona','revision':REVISION,
        'rights':'CAiRE repository MIT notice and underlying PersonaChat CC BY 4.0 retained; Lin et al. 2021 and Zhang et al. 2018'}
    write_json(a.output/'corpus.json',{'version':'vipi-xpersona-validation-1','source_only':True,
        'partition':'official human-adapted validation; diagnostic development','languages':codes,'expected_pairs':pairs,'cases':cases,'attribution':attribution})
    write_json(a.output/'phrase-protocol.json',{'schema':'vipi-local-phrase-probe-1','qa_run_id':a.apple_run_id,
        'scope':'Actual conversation turns plus first lexical token for harness plumbing; no reference target',
        'window_extents':[],'maximum_phrase_characters':192,'maximum_window_words':8,'meaning_acceptance':False,'samples':samples})
    write_json(a.output/'receipt.json',{'schema':'vipi-xpersona-validation-probe-1','messages':len(cases),
        'direction_cases':len(samples),'pairs':pairs,'reports':reports,'source_receipt_sha256':sha_file(receipt_path),
        'corpus_sha256':sha_file(a.output/'corpus.json'),'protocol_sha256':sha_file(a.output/'phrase-protocol.json'),
        'selector_sha256':sha_file(Path(__file__)),'translation_gold':False,'linguistic_acceptance':False,
        'official_test_files_parsed':False,
        'selection':'Independent file-dialogue-index hash, then lowest turn hash; duplicate whole views/selected text and training-text duplicates excluded; no model/dictionary filtering',
        'limits':['Human-adapted persona role-play, not organic private chat or a population survey.',
            'Same full utterance inventories are deduplicated; partial overlapping views and shared personas may remain.',
            'Dialogue rows and turns across languages are adapted, not literal gold or independent samples.',
            'Only validation is sampled; all official test files remain reserved.',
            'All inspected validation cases are development diagnostics, never independent acceptance.']})
    print(json.dumps({'messages':len(cases),'direction_cases':len(samples),'pairs':pairs,
        'selection_counts':{r['language']:r['selection_counts'] for r in reports}}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--languages',nargs='+',choices=sorted(SOURCE_LANGUAGES.values()),default=['it','ja','ko'])
    p.add_argument('--per-language',type=int,default=100);p.add_argument('--apple-run-id',default='008');main(p.parse_args())
