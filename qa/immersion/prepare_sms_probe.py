#!/usr/bin/env python3
"""Freeze contributor-separated real-message probes without target references.

Research only: original public SMS text stays in QA storage. Selection never
consults a vocabulary pack, model output, concept label or target sentence.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import icu
from conversation_corpus import LANGUAGES, sha_file, write_json
from conversation_priority import sms_records, split_sms_records


def first_word(text, language):
    value=icu.UnicodeString(text)
    iterator=icu.BreakIterator.createWordInstance(icu.Locale(language))
    iterator.setText(value);start=iterator.first()
    for end in iterator:
        word=str(value[start:end])
        if any(c.isalpha() for c in word):return start,end,word
        start=end
    return None


def prepare(rows, count):
    selected=defaultdict(list);counts=Counter()
    for language,identifier,text,partition in rows:
        if partition!='reserved':continue
        counts[language+':reserved']+=1
        if not 1<=len(text)<=280:
            counts[language+':excluded_length']+=1;continue
        focus=first_word(text,language)
        if focus is None:
            counts[language+':excluded_no_word']+=1;continue
        counts[language+':eligible']+=1
        digest=hashlib.sha256(('vipi-nus-native-probe-v1:'+language+':'+identifier+':'+text).encode()).hexdigest()
        selected[language].append((digest,text,focus))
    cases=[];samples=[];languages=list(LANGUAGES.values())
    for language in sorted(selected):
        if len(selected[language])<count:raise ValueError('Insufficient reserved messages')
        chosen=sorted(selected[language])[:count]
        counts[language+':selected']=len(chosen)
        for digest,text,(start,end,word) in chosen:
            identifier='nus-'+digest[:24]
            cases.append({'id':identifier,'text':{language:text}})
            for target in languages:
                if language==target:continue
                samples.append({'case':identifier,'source':language,'target':target,'original':text,
                    'start':start,'end':end,'source_word':word,
                    'evaluation_scope':'reserved contributor-separated NUS SMS; no target reference'})
    return cases,samples,dict(counts)


def main(args):
    args.output.mkdir(parents=True,exist_ok=False)
    rows,partition=split_sms_records(list(sms_records(args.source)))
    cases,samples,counts=prepare(rows,args.per_language)
    attribution={'source':'https://github.com/kite1988/nus-sms-corpus',
        'release':'2015-03-09; commit bf0a365170d324e61e4025edf363d400f1edd1a6',
        'rights':'Authors describe the consented release as public domain; research inputs only'}
    corpus={'version':'vipi-nus-sms-reserved-1','source_only':True,'partition':'reserved',
        'languages':list(LANGUAGES.values()),'expected_pairs':18,'cases':cases,'attribution':attribution}
    protocol={'schema':'vipi-local-phrase-probe-1','qa_run_id':args.apple_run_id,
        'scope':'Whole real messages plus first lexical token; focus is harness plumbing, not a selected substitution',
        'window_extents':[],'maximum_phrase_characters':192,'maximum_window_words':8,
        'meaning_acceptance':False,'samples':samples}
    write_json(args.output/'corpus.json',corpus)
    write_json(args.output/'phrase-protocol.json',protocol)
    write_json(args.output/'receipt.json',{'schema':'vipi-nus-native-probe-1','counts':counts,
        'messages':len(cases),'direction_cases':len(samples),'pairs':18,'partition':partition,
        'source_receipt_sha256':sha_file(args.source/'receipt.json'),
        'corpus_sha256':sha_file(args.output/'corpus.json'),
        'protocol_sha256':sha_file(args.output/'phrase-protocol.json'),
        'selector_sha256':sha_file(Path(__file__)),
        'partitioner_sha256':sha_file(Path(__file__).with_name('conversation_priority.py')),
        'selection':'Lowest hash of version, language, source record ID and exact text; no dictionary/model consultation',
        'translation_gold':False,'human_quality_acceptance':False,
        'limits':['Older regional English/Chinese SMS, not a representative ten-language chat sample.',
          'Up to 280 code points, at least one lexical token; excluded message counts retained.',
          'Contributor separated and reserved duplicate purged; not proven participant/conversation separation.',
          'Do not promote these reserved messages into authoring examples.']})
    print(json.dumps({'messages':len(cases),'direction_cases':len(samples),'counts':counts}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--per-language',type=int,default=200);p.add_argument('--apple-run-id',default='003')
    a=p.parse_args()
    if not 1<=a.per_language<=500:raise SystemExit('Per-language bound is 1..500')
    if len(a.apple_run_id)!=3 or not a.apple_run_id.isascii() or not a.apple_run_id.isdigit():raise SystemExit('Three-digit run ID required')
    main(a)
