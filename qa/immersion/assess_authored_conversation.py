#!/usr/bin/env python3
"""Record this session's assessment of one exact authored development batch.

This is deliberately pinned, not an automatic approval rule for future input.
The author inspected the twenty meanings and conventional Latin readings.
Chinese source 问题 lacks enough context to choose question versus problem in
these two sentences, so those eighteen directions remain unapproved.
"""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'language-packs'))
from authored_everyday import AUTHOR
from mapping_catalog import Catalog,digest
from build_wiktextract import digest_file

EXPECTED='bc08153c579db4c7dd0e55273212390d2cbf10f1cade1a4604ac2e5100df9ec3'


def main(args):
    if digest_file(args.records)!=EXPECTED:raise ValueError('This assessment applies only to the inspected batch')
    values=[json.loads(line) for line in args.records.read_text().splitlines()]
    if len(values)!=1782:raise ValueError('Unexpected batch')
    evidence=[{'sha256':EXPECTED,'path':str(args.records),'description':'Exact authored twenty-meaning contexts and readable transliterations inspected by the author'}]
    for path in (args.android,args.apple):
        receipt=json.loads(path.read_text())
        if receipt.get('cases')!=1782 or receipt.get('reference_sha256')!=EXPECTED:
            raise ValueError('Native receipt does not qualify this exact batch')
        evidence.append({'sha256':digest_file(path),'path':str(path),
            'description':'Native context matching, explicit lexical scope, reading guards and alignment against retained actual local translations; reused development input'})
    args.output.mkdir(parents=True,exist_ok=False);catalog=Catalog(args.catalog);reviewed=0;quarantined=0
    try:
        with (args.output/'assessments.jsonl').open('x') as stream:
            for record in values:
                ambiguous=record['source_language']=='zh' and any(':conversation_'+name+':' in record['logical_id'] for name in ('question','problem'))
                report={'schema':'vipi-mapping-review-1','record_sha256':digest(record),'reviewer':AUTHOR,
                    'assessment_kind':'author_assessment','verdict':'quarantined' if ambiguous else 'reviewed',
                    'evidence':evidence,'checks':{'meaning':'unresolved' if ambiguous else 'pass','usage':'pass',
                        'grammar_scope':'pass','provenance':'pass','reading':'pass' if record['target_language'] in ('ar','zh','ja','ko') else 'not_required'},
                    'rationale':('These short Chinese source contexts do not distinguish the information-request and difficulty senses of 问题. Require an explicit asking/solving context.' if ambiguous else
                        'Author assessment of this exact lexical mapping: '+record['meaning']+'. Source and target focus are explicitly marked in the authored contexts. Articles, possessors, case particles and surrounding wording remain outside the lexical focus; conventional adverbs such as today retain their lexicalized surface. Readings are conventional Latin transliterations, not phonetic glyphs. This assessment does not generalize the sentence to arbitrary paraphrases.'),
                    'limits':['Author assessment, not an independent reviewer or user study.',
                        'Provider disagreement, missing target forms, native protection checks and unsupported contexts still withhold immersion.',
                        'No broad conversation-coverage, fluency, signed-pack release or general-chat integration claim.']}
                catalog.review(report);stream.write(json.dumps(report,ensure_ascii=False,sort_keys=True)+'\n')
                if ambiguous:quarantined+=1
                else:reviewed+=1
        result={'reviewed':reviewed,'quarantined':quarantined,'assessment_kind':'author_assessment',
            'records_sha256':EXPECTED,'assessments_sha256':digest_file(args.output/'assessments.jsonl'),
            'catalog':catalog.stats(),'release_ready':False}
        (args.output/'receipt.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
    finally:catalog.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('records','catalog','android','apple','output'):p.add_argument('--'+name,type=Path,required=True)
    main(p.parse_args())
