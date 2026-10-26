#!/usr/bin/env python3
"""Prepare dialogue-separated Arabic/French probes and training-only priorities.

Stream the publisher archive; never unpack its 1.4 GB of dialogue/database data.
Parallel dialogue IDs are not reference translations: names and places differ.
Requires ijson==3.4.0.post0 and the existing PyICU corpus environment.
"""
import argparse
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
import zipfile
import ijson
from conversation_corpus import LANGUAGES,key,sha_file,write_json
from conversation_priority import tokenize
from fetch_multi3woz import REVISION
from prepare_sms_probe import first_word


def fingerprint(language,dialogue,turn,text):
    return hashlib.sha256(f'vipi-multi3woz-probe-1:{language}:{dialogue}:{turn}:{text}'.encode()).hexdigest()


def dialogue_fingerprint(language,dialogue):
    return hashlib.sha256(f'vipi-multi3woz-dialogue-2:{language}:{dialogue}'.encode()).hexdigest()


def is_user(row):
    # SNG1213 has an extra SYSTEM turn. Explicit publisher speaker labels
    # outrank turn parity; otherwise that system message becomes a user probe.
    speaker=row.get('speaker')
    if speaker not in ('USER','SYSTEM'):raise ValueError('Unexpected speaker label')
    user=speaker=='USER'
    if bool(row['metadata'])==user:raise ValueError('Speaker/metadata disagreement')
    return user


def choose(language,rows,non_test_texts,count):
    dialogs=defaultdict(list);counts=Counter();seen=set();selected=[]
    for dialogue,turn,text in rows:
        counts['official_test_user_turns']+=1
        if not 1<=len(text)<=280:counts['excluded_length']+=1;continue
        focus=first_word(text,language)
        if focus is None:counts['excluded_no_word']+=1;continue
        if key(text) in non_test_texts:counts['excluded_train_dev_duplicate']+=1;continue
        dialogs[dialogue].append((fingerprint(language,dialogue,turn,text),dialogue,turn,text,focus))
    # Each dialogue contributes at most one message, regardless of its length.
    # Rank dialogues independently of their number of eligible turns. Ranking
    # their minimum turn hash instead would favor longer conversations.
    candidates=[min(dialogs[dialogue]) for dialogue in sorted(dialogs,
        key=lambda dialogue:(dialogue_fingerprint(language,dialogue),dialogue))]
    counts['eligible_dialogues']=len(candidates)
    for row in candidates:
        if key(row[3]) in seen:counts['excluded_selected_text_duplicate']+=1;continue
        seen.add(key(row[3]));selected.append(row)
        if len(selected)==count:break
    if len(selected)!=count:raise ValueError('Insufficient distinct eligible dialogues')
    return selected,dict(counts)


def main(a):
    if not 1<=a.per_language<=500:raise ValueError('Bounded probe required')
    if len(a.apple_run_id)!=3 or not a.apple_run_id.isascii() or not a.apple_run_id.isdigit():raise ValueError('Three-digit run ID required')
    receipt_path=a.source/'receipt.json';receipt=json.loads(receipt_path.read_text())
    if receipt['revision']!=REVISION:raise ValueError('Wrong publisher revision')
    for asset in receipt['assets']:
        if sha_file(a.source/asset['file'])!=asset['sha256']:raise ValueError('Changed publisher asset')
    a.output.mkdir(parents=True,exist_ok=False);cases=[];samples=[];summaries=[];selected_ids={}
    codes=list(LANGUAGES.values())
    with zipfile.ZipFile(a.source/'data.zip') as archive:
        if any(any(k in p.filename.lower() for k in ('license','copying')) for p in archive.infolist()):
            raise ValueError('Inspect archive-specific license before processing')
        for language,name in [('ar','Arabic'),('fr','French')]:
            prefix='data/'+name+'/'
            reserved=set(archive.read(prefix+'testListFile.txt').decode().split())
            development=set(archive.read(prefix+'valListFile.txt').decode().split())
            if len(reserved)!=1000 or len(development)!=1000 or reserved&development:raise ValueError('Unexpected official splits')
            non_test_texts=set();test_rows=[];counts=Counter();frequency=Counter();all_ids=set()
            with archive.open(prefix+'data.json') as stream:
                for dialogue,value in ijson.kvitems(stream,''):
                    if dialogue in all_ids:raise ValueError('Duplicate dialogue ID')
                    all_ids.add(dialogue)
                    partition='test' if dialogue in reserved else 'development' if dialogue in development else 'train'
                    counts[partition+'_dialogues']+=1
                    for turn,row in enumerate(value['log']):
                        text=row['text']
                        if not isinstance(text,str) or len(text)>10000:raise ValueError('Unexpected turn text')
                        user=is_user(row)
                        counts['speaker_parity_exceptions']+=user!=(turn%2==0)
                        counts[partition+('_user_turns' if user else '_system_turns')]+=1
                        if partition!='test':non_test_texts.add(key(text))
                        if partition=='train' and user:frequency.update(tokenize(text,language))
                        if partition=='test' and user:test_rows.append((dialogue,turn,text))
            # The pinned archive has 9,160 dialogues, but its inherited split
            # lists each name 1,000 IDs, of which 860 are actually present.
            # Verify this observed snapshot and retain every absent ID.
            if (len(all_ids),len(reserved&all_ids),len(development&all_ids))!=(9160,860,860):
                raise ValueError('Changed published corpus/split membership')
            selected,selection=choose(language,test_rows,non_test_texts,a.per_language)
            selected_ids[language]=[r[1] for r in selected]
            for digest,dialogue,turn,text,(start,end,word) in selected:
                identifier='m3w-'+digest[:24]
                cases.append({'id':identifier,'text':{language:text}})
                for target in codes:
                    if target==language:continue
                    samples.append({'case':identifier,'source':language,'target':target,'original':text,
                        'start':start,'end':end,'source_word':word,
                        'evaluation_scope':'one official-test user turn per task-oriented dialogue; no literal translation reference'})
            summaries.append({'language':language,'counts':dict(counts),'selection_counts':selection,
                'split_list_ids_absent_from_archive':{'test':sorted(reserved-all_ids),'development':sorted(development-all_ids)},
                'train_user_word_frequencies':frequency.most_common(100),
                'frequency_limit':'Mechanical token frequencies include names and grammar; training split only'})
    attribution={'source':'https://github.com/cambridgeltl/multi3woz','revision':REVISION,
        'rights':'MIT; Songbo Hu and Multi3WOZ contributors. Retained publisher LICENSE/README; archive has no separate license notice.'}
    write_json(a.output/'corpus.json',{'version':'vipi-multi3woz-official-test-2','source_only':True,
        'partition':'available official-test dialogues with cross-partition duplicate exclusions','languages':codes,
        'expected_pairs':18,'cases':cases,'attribution':attribution})
    write_json(a.output/'phrase-protocol.json',{'schema':'vipi-local-phrase-probe-1','qa_run_id':a.apple_run_id,
        'scope':'Whole actual dialogue user turns plus first lexical token; focus is harness plumbing, not chosen immersion',
        'window_extents':[],'maximum_phrase_characters':192,'maximum_window_words':8,
        'meaning_acceptance':False,'samples':samples})
    write_json(a.output/'receipt.json',{'schema':'vipi-multi3woz-native-probe-2','messages':len(cases),
        'direction_cases':len(samples),'pairs':18,'reports':summaries,'selected_dialogue_ids':selected_ids,
        'shared_selected_parallel_dialogue_ids':len(set(selected_ids['ar'])&set(selected_ids['fr'])),
        'source_receipt_sha256':sha_file(receipt_path),'corpus_sha256':sha_file(a.output/'corpus.json'),
        'protocol_sha256':sha_file(a.output/'phrase-protocol.json'),'selector_sha256':sha_file(Path(__file__)),
        'ijson_version':ijson.__version__,'translation_gold':False,'linguistic_acceptance':False,
        'selection':'Independent dialogue-ID hash ranking, then lowest fixed hash eligible user turn per dialogue; skip duplicate selected text; no dictionary/model filtering',
        'limits':['Task-oriented, culturally adapted dialogue, not a representative friend-chat sample.',
            'Each official 1000-ID split list has only 860 IDs present in the pinned archive; missing IDs retained in the report.',
            'One user turn per dialogue; neither author nor participant separation is established.',
            'Text deduplication can exclude a ranked dialogue; this is a reproducible diagnostic sample, not a population-random survey.',
            'Parallel dialogue IDs across languages are dependent; adapted text and en_text are not literal gold translations.',
            'Selected official-test text must not enter authoring; inspected cases become diagnostic material.']})
    print(json.dumps({'messages':len(cases),'direction_cases':len(samples),'pairs':18,
        'counts':[{k:v for k,v in r.items() if k not in ('train_user_word_frequencies','frequency_limit')} for r in summaries]}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--per-language',type=int,default=200);p.add_argument('--apple-run-id',default='006')
    main(p.parse_args())
