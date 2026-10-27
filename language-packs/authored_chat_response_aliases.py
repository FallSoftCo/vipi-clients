#!/usr/bin/env python3
"""Explicit bidirectional written aliases and uppercase short-response inputs.

Preserve canonical whole translations; alternate target spellings have lexical
scope only. No general case folding or language-detection threshold change.
"""
import argparse
from pathlib import Path
import authored_chat_responses as base
from authored_everyday import mapping
from build_wiktextract import canonical,digest_file
from mapping_catalog import digest,validate

BASE_SHA='786ba051dacdb659199ffe70c60530d23caf7f88af56782c142f32a550cc1447'
ROMAN={'en','es','fr','de','it','pt','sw'}

def variants(topic,language,sentence):
    values=set(base.forms(topic,language,sentence))
    if language in ROMAN:values.update(value.upper() for value in list(values))
    return sorted(values)

def records():
    if digest_file(Path(base.__file__))!=BASE_SHA:raise ValueError('Changed assessed response author')
    for topic,(meaning,line) in base.DATA.items():
        parsed=base.cells(topic,line)
        for source,(sentence,_) in parsed.items():
            old_sources=set(base.forms(topic,source,sentence))
            for target,(translation,reading) in parsed.items():
                if source==target:continue
                alternatives=sorted({base.focus(v) for v in variants(topic,target,translation)}-{base.focus(translation)})
                for original in variants(topic,source,sentence):
                    choices=[(translation,True)] if original not in old_sources else []
                    choices += [(right,False) for right in alternatives]
                    for right_context,whole in choices:
                        left,right=base.focus(original),base.focus(right_context)
                        identity='chat_response_alias_'+digest([topic,source,target,original,right_context,whole])[:32]
                        row=mapping(identity,source,target,left,right,original,right_context,meaning,base.focus(reading) if reading else '')
                        row['usage'].update(context_extent='local_phrase',lexical_unit=True,whole_reference=whole,
                            context_generalization='explicit assessed reply spelling or case alias, never arbitrary normalization',
                            source_frame_span=row['source_span'][:],target_frame_span=row['target_span'][:],
                            source_frame_pattern=[{'focus':left}],target_frame_pattern=[{'focus':right}],
                            permitted_context=meaning+'; exact unique complete native counterparts must both occur',
                            abstain_when=['Changed or incomplete response, repeated occurrences or competing meanings/readings.',
                                'Protected identifiers or invalid native boundaries.',
                                'Unlisted spellings, question punctuation, or source forms cannot borrow a whole reference.'])
                        row['provenance'].update(base_author_sha256=BASE_SHA,
                            lexical_source='Exact forms and meanings from the assessed short-response batch; explicit uppercase variants only',
                            whole_reference_eligibility='Only newly listed uppercase source responses to the same canonical complete translation' if whole else 'False: alternate target spellings are lexical-only',
                            priority_basis='Native forward/reverse short-reply regression; no reserved conversation text read')
                        validate(row);yield row

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();rows=list(records());assert len(rows)==len({r['logical_id'] for r in rows})
    args.output.mkdir(parents=True,exist_ok=False);p=args.output/'records.jsonl';p.write_text(''.join(canonical(r)+'\n' for r in rows))
    print(canonical(dict(records=len(rows),whole_references=sum(r['usage']['whole_reference'] for r in rows),
        records_sha256=digest_file(p),authoring_source_sha256=digest_file(Path(__file__)),author_assessment_pending=True,release_ready=False)))
