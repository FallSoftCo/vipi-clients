#!/usr/bin/env python3
"""Development-only frequency audit of public sentences and consented SMS.

No message contents or contributor metadata are printed in the report. Public
corpus text is kept in research storage, never uploaded from app users.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3
import xml.etree.ElementTree as ET
import zipfile
import icu
from conversation_corpus import Components, LANGUAGES, key, sha_file, write_json


def tokenize(text,language):
    iterator=icu.BreakIterator.createWordInstance(icu.Locale(language))
    value=icu.UnicodeString(text);iterator.setText(value);start=iterator.first()
    for end in iterator:
        word=str(value[start:end]);start=end
        if any(c.isalpha() for c in word): yield key(word)


def sms_records(folder):
    receipt=json.loads((folder/'receipt.json').read_text())
    for asset in receipt['assets']:
        path=folder/asset['file']
        if sha_file(path)!=asset['sha256']: raise ValueError('SMS source integrity mismatch')
        if path.suffix!='.zip': continue
        language='en' if '_en_' in path.name else 'zh'
        with zipfile.ZipFile(path) as archive:
            if len(archive.infolist())!=1: raise ValueError('Unexpected SMS archive')
            member=archive.infolist()[0]
            if member.file_size>60_000_000 or not member.filename.endswith('.xml'): raise ValueError('SMS size/type bound')
            with archive.open(member) as stream:
                for event,node in ET.iterparse(stream,events=['end']):
                    if node.tag!='message': continue
                    # Retain no phone numbers, location, age, or profile.
                    text=node.findtext('text') or ''
                    contributor=node.findtext('source/userProfile/userID') or ''
                    identifier=node.get('id')
                    if not identifier or len(text)>10000: raise ValueError('Unexpected SMS record')
                    yield language,identifier,text,contributor
                    node.clear()


def sms_partition(folder):
    """Reserve contributors first, then remove cross-partition duplicates.

    Merging contributors through every common "okay" message creates one huge
    component and an unusable test set. Removing overlapping reserved texts
    preserves contributor separation without misrepresenting that graph.
    """
    records=list(sms_records(folder));output,metadata=partition_sms_records(records)
    metadata['source_receipt_sha256']=sha_file(folder/'receipt.json')
    return output,metadata


def partition_sms_records(records):
    rows,metadata=split_sms_records(records)
    return [(language,text) for language,identifier,text,split in rows if split=='development'],metadata


def split_sms_records(records):
    assignments={};groups=Counter();train_texts=set();partitions=Counter();output=[]
    for language,identifier,text,contributor in records:
        groups[contributor]+=1
        digest=hashlib.sha256(('vipi-nus-contributor-v2:'+contributor).encode()).digest()
        known=contributor.strip().casefold() not in ('','unknown','null','none','n/a','0')
        split='reserved' if known and int.from_bytes(digest[:8],'big')%100<15 else 'development'
        assignments[contributor]=split
        if split=='development':train_texts.add((language,key(text)))
    reserved_texts=set()
    for language,identifier,text,contributor in records:
        split=assignments[contributor];normalized=(language,key(text))
        if split=='reserved':
            if normalized in train_texts:split='excluded_cross_partition_duplicate'
            elif normalized in reserved_texts:split='excluded_reserved_duplicate'
            else:reserved_texts.add(normalized)
        partitions[language+':'+split]+=1
        output.append((language,identifier,text,split))
    return output,{'split_recipe':'vipi-nus-contributor-v2:85-development:15-reserved; purge overlapping reserved text',
        'partitions':dict(partitions),'contributors':len(groups),'largest_contributor_messages':max(groups.values()),
        'raw_messages':len(records),'reserved_unique_texts':len(reserved_texts),
        'contributor_grouping_scope':'Same contributor ID across languages; unknown IDs always development; not proof of participant-disjoint conversations'}


def audit(language,texts,forms,grammar):
    counts=Counter();words=Counter();missing=Counter();known_contexts=set(forms['contexts'])
    for text in texts:
        counts['messages']+=1
        tokens=list(tokenize(text,language));counts['word_tokens']+=len(tokens)
        recognized=0;eligible=0;lexical=0
        for token in tokens:
            if token in grammar:
                counts['grammatical_tokens_excluded']+=1;continue
            eligible+=1;words[token]+=1
            if token in forms['surfaces']:recognized+=1
            else:missing[token]+=1
            if token in forms.get('lexicon',set()):lexical+=1
        counts['non_guarded_word_tokens']+=eligible
        counts['recognized_non_guarded_surfaces']+=recognized
        counts['messages_with_any_recognized_non_guarded_surface']+=recognized>0
        counts['messages_exactly_matching_a_catalog_context']+=key(text) in known_contexts
        if 'lexicon' in forms:
            counts['full_lexicon_recognized_non_guarded_surfaces']+=lexical
            counts['messages_with_any_full_lexicon_surface']+=lexical>0
    denominator=counts['non_guarded_word_tokens']
    return {'language':language,'counts':dict(counts),
        'source_surface_recognition':counts['recognized_non_guarded_surfaces']/denominator if denominator else None,
        'top_non_guarded_surfaces':words.most_common(100),'top_missing_surfaces':missing.most_common(100)}


def main(args):
    grammar=json.loads(args.grammar.read_text())['terms']
    forms={language:{'surfaces':set(),'contexts':set()} for language in LANGUAGES.values()}
    with sqlite3.connect(args.catalog.resolve().as_uri()+'?mode=ro',uri=True) as catalog:
        for language,surface,payload in catalog.execute('SELECT source_language,source_key,payload FROM revisions'):
            forms[language]['surfaces'].add(key(surface))
            forms[language]['contexts'].add(key(json.loads(payload)['source_context']))
    if args.lexicon:
        for values in forms.values():values['lexicon']=set()
        with sqlite3.connect(args.lexicon.resolve().as_uri()+'?mode=ro&immutable=1',uri=True) as lexicon:
            for language,word in lexicon.execute('SELECT DISTINCT language,form FROM terms'):
                if language in forms:forms[language]['lexicon'].add(key(word))
    reports=[]
    if args.corpus:
        with sqlite3.connect(args.corpus.resolve().as_uri()+'?mode=ro&immutable=1',uri=True) as corpus:
            for language in LANGUAGES.values():
                texts=(row[0] for row in corpus.execute("SELECT text FROM sentences WHERE language=? AND partition='development'",(language,)))
                result=audit(language,texts,forms[language],set(map(key,grammar[language])))
                reports.append({'corpus':'Tatoeba','partition':'development',**result})
                print(json.dumps({'corpus':'Tatoeba','language':language,'counts':result['counts']}),flush=True)
    sms_metadata=None
    if args.sms:
        messages,sms_metadata=sms_partition(args.sms)
        for language in ('en','zh'):
            result=audit(language,(text for lang,text in messages if lang==language),forms[language],set(map(key,grammar[language])))
            reports.append({'corpus':'NUS SMS','partition':'development',**result})
            print(json.dumps({'corpus':'NUS SMS','language':language,'counts':result['counts']}),flush=True)
    write_json(args.output,{'schema':'vipi-conversation-priority-1','reports':reports,'sms_partition':sms_metadata,
        'icu_version':icu.ICU_VERSION,'pyicu_version':icu.VERSION,'analyzer_sha256':sha_file(Path(__file__)),
        'catalog_sha256':sha_file(args.catalog),'grammar_sha256':sha_file(args.grammar),
        'lexicon_sha256':sha_file(args.lexicon) if args.lexicon else None,
        'corpus_sha256':sha_file(args.corpus) if args.corpus else None,
        'linguistic_acceptance':False,'runtime_integration':False,
        'limits':['Dictionary-source recognition is not contextual correctness or target-pair coverage.',
          'Non-guarded tokens may still include names, fillers and grammatical forms; not gold content-word coverage.',
          'NUS SMS is an older Singapore/Chinese texting sample, not all modern demographics or languages.',
          'Contributor grouping and duplicate grouping can produce unequal partitions.',
          'Exact catalog context matches do not measure finite patterns or the full native immersion pipeline.']})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('catalog','grammar','output'):p.add_argument('--'+name,type=Path,required=True)
    for name in ('corpus','sms','lexicon'):p.add_argument('--'+name,type=Path)
    main(p.parse_args())
