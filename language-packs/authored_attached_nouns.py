#!/usr/bin/env python3
"""Finite attached noun forms derived only from exact previously assessed units.

The contextual scope is newly authored and needs its own content-bound review.
No evaluation messages, generic dictionary promotions, runtime stemming or
new lexical translations enter this batch. Sentence grammar stays outside focus.
"""
import argparse
import itertools
import json
import sqlite3
from contextlib import closing
from pathlib import Path
import authored_conversation as base
import authored_conversation_expansion as expansion
import authored_conversation_routines as routines
from authored_everyday import mapping
from authored_everyday_units import MEANINGS
from authored_people_ideas_units import LANGUAGES, forms
from authored_plural_units import DATA
from build_wiktextract import canonical, digest_file
from mapping_catalog import digest, validate

BASELINE_SHA='d655845001761231feaed260bd4793cb31a56d6f2f477cf33f517ce74c0e384e'
SW_LOCATIVES={
 'school_place':['shule'], 'office_place':['ofisi'], 'hotel_place':['hoteli'],
 'restaurant_place':['mkahawa','migahawa'], 'door_physical':['mlango','milango'],
 'car':['gari','magari'],
}
# Nyumbani can mean home independently of the house-building sense. Multiword
# locatives can have discontinuous noun focuses. Neither is licensed here.
EXCLUDED_SW={'nyumba','nyumbani','uwanja wa ndege','viwanja vya ndege'}


def meaning_for(topic):
    return MEANINGS.get(topic) or dict(base.DATA,**expansion.DATA,**routines.DATA)[topic][0]


def korean_suffixes(noun):
    last=ord(noun[-1])
    if not 0xAC00<=last<=0xD7A3:raise ValueError('An explicitly listed Hangul noun is required')
    consonant=(last-0xAC00)%28 != 0
    return ['은' if consonant else '는','이' if consonant else '가','을' if consonant else '를',
            '과' if consonant else '와','도','만','에','에서','의']


def allowed_forms():
    korean={(word,meaning_for(topic)) for topic,line in DATA.items()
        for word,_ in forms(line.split('|')[LANGUAGES.index('ko')],'ko')}
    swahili={(word,meaning_for(topic)) for topic,words in SW_LOCATIVES.items() for word in words}
    assert not any(word in EXCLUDED_SW for word,_ in swahili)
    return korean,swahili


def load_units(directory):
    if digest_file(directory/'catalog.json')!=BASELINE_SHA:raise ValueError('Changed baseline catalog')
    catalog=json.loads((directory/'catalog.json').read_text());seen={}
    for pair in catalog['packs']:
        path=directory/(pair['id']+'.sqlite')
        if path.stat().st_size!=pair['bytes'] or digest_file(path)!=pair['sha256']:raise ValueError('Changed baseline pack')
        with closing(sqlite3.connect('file:'+str(path.resolve())+'?mode=ro',uri=True)) as db:
            for payload,evidence in db.execute('SELECT payload,evidence FROM mappings ORDER BY id'):
                row=json.loads(payload)
                if row.get('lexical_unit') is not True:continue
                envelope=json.loads(evidence)
                if digest(envelope['record'])!=row['record_sha256']:raise ValueError('Changed assessed source evidence')
                key=(row['source_language'],row['target_language'],row['source'],row['target'],row['meaning'])
                if key in seen and seen[key]['reading']!=row['reading']:raise ValueError('Conflicting exact reading')
                seen.setdefault(key,row)
    return [seen[key] for key in sorted(seen)]


def records(units):
    korean,swahili=allowed_forms()
    def attachments(language,word,meaning):
        if language=='ko' and (word,meaning) in korean:return korean_suffixes(word)
        if language=='sw' and (word,meaning) in swahili:return ['ni']
        return None
    for old in units:
        source,target=old['source_language'],old['target_language'];left,right=old['source'],old['target']
        meaning=old['meaning'];left_suffixes=attachments(source,left,meaning);right_suffixes=attachments(target,right,meaning)
        if not left_suffixes and not right_suffixes:continue
        for attached_left,attached_right in itertools.product([False,True] if left_suffixes else [False],[False,True] if right_suffixes else [False]):
            if not attached_left and not attached_right:continue
            suffixes=[left_suffixes if attached_left else None,right_suffixes if attached_right else None]
            originals=[left+(suffixes[0][0] if suffixes[0] else ''),right+(suffixes[1][0] if suffixes[1] else '')]
            identity='attached_noun_'+digest([source,target,left,right,meaning,attached_left,attached_right])[:32]
            row=mapping(identity,source,target,left,right,*originals,meaning,old['reading'])
            row['usage'].update(context_extent='local_phrase',lexical_unit=False,whole_reference=False,
                source_lexical_unit=not attached_left,target_lexical_unit=not attached_right,
                context_generalization='finite explicitly authored noun attachment; no inferred runtime morphology',
                permitted_context=meaning+'; unique corresponding full forms in both original and actual whole translation',
                abstain_when=['Unlisted attachment or an internal substring of a larger native word.',
                    'Missing or repeated counterpart, competing meaning or conflicting reading.',
                    'Protected identifiers, unlisted noun forms, or unsupplied target-script reading.'])
            for side,noun,context,ending in zip(['source','target'],[left,right],originals,suffixes,strict=True):
                row['usage'][side+'_frame_span']=[0,len(context)]
                row['usage'][side+'_frame_pattern']=[{'focus':noun}]+([{'slot':ending}] if ending else [])
            row['provenance'].update(baseline_catalog_sha256=BASELINE_SHA,baseline_mapping_id=old['id'],
                baseline_record_sha256=old['record_sha256'],lexical_source='Exact previously assessed form, sense and reading; no new translation pair',
                attachment_source='Project-authored finite Korean particles or Swahili locative -ni',
                priority_basis='Language morphology identified independently of evaluation utterances',
                whole_reference_eligibility='False: noun carriers do not represent complete message translations')
            validate(row);yield row


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();rows=list(records(load_units(args.baseline)))
    assert len(rows)==len({row['logical_id'] for row in rows})
    args.output.mkdir(parents=True,exist_ok=False);path=args.output/'records.jsonl'
    path.write_text(''.join(canonical(row)+'\n' for row in rows))
    print(canonical({'records':len(rows),'directions':len({(r['source_language'],r['target_language']) for r in rows}),
        'records_sha256':digest_file(path),'authoring_source_sha256':digest_file(Path(__file__)),
        'author_assessment_pending':True,'release_ready':False}))
