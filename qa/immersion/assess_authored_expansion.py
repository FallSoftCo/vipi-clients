#!/usr/bin/env python3
"""Content-bound author assessment of the second inspected everyday batch.

This records the author's assessment, not automatic approval of future batches
or independent approval of the providers' translations.
"""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'language-packs'))
from authored_everyday import AUTHOR
from mapping_catalog import Catalog,digest
from build_wiktextract import digest_file

EXPECTED='cdaed8968c885f83e6207a746de7ee30cbe92b6aa7a05a964a06a6c591189a23'


def main(a):
    if digest_file(a.records)!=EXPECTED:raise ValueError('Assessment applies only to inspected revision002')
    records=[json.loads(line) for line in a.records.read_text().splitlines()]
    if len(records)!=1800:raise ValueError('Unexpected batch size')
    evidence=[{'sha256':EXPECTED,'path':str(a.records),'description':'Author-inspected twenty-meaning batch; German friendship and hotel-room scope clarified before qualification'}]
    for path in (a.android,a.apple):
        observed=json.loads(path.read_text())
        if observed.get('cases')!=1800 or observed.get('reference_sha256')!=EXPECTED:raise ValueError('Wrong native reference evidence')
        if {r['case'] for r in observed['results']}!={r['logical_id'] for r in records}:raise ValueError('Incomplete case evidence')
        evidence.append({'sha256':digest_file(path),'path':str(path),'description':'Native explicit source/target scope and required readings against retained actual provider output; development cases'})
    a.output.mkdir(parents=True,exist_ok=False);catalog=Catalog(a.catalog)
    try:
        with (a.output/'assessments.jsonl').open('x') as stream:
            for record in records:
                report={'schema':'vipi-mapping-review-1','record_sha256':digest(record),'reviewer':AUTHOR,
                    'assessment_kind':'author_assessment','verdict':'reviewed','evidence':evidence,
                    'checks':{'meaning':'pass','usage':'pass','grammar_scope':'pass','provenance':'pass',
                        'reading':'pass' if record['target_language'] in ('ar','zh','ja','ko') else 'not_required'},
                    'rationale':'Author assessment of this exact context: '+record['meaning']+'. The marked lexical focus and conventional Latin reading were inspected in the ten authored language references. Articles, possessors and case particles stay outside the focus. Hotel-room and German friendship wording supply the intended meaning; no arbitrary paraphrase is authorized.',
                    'limits':['Author assessment, not an independent reviewer or user study.',
                        'This approves the authored mapping, not every provider output, region, or unobserved context.',
                        'Identical source/target spelling, provider variation and native ambiguity/reading guards may withhold immersion.',
                        'No majority-conversation, general-chat integration, signed-release or fluency claim.']}
                catalog.review(report);stream.write(json.dumps(report,ensure_ascii=False,sort_keys=True)+'\n')
        result={'reviewed':len(records),'assessment_kind':'author_assessment','records_sha256':EXPECTED,
            'assessments_sha256':digest_file(a.output/'assessments.jsonl'),'catalog':catalog.stats(),'release_ready':False}
        (a.output/'receipt.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
    finally:catalog.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('records','catalog','android','apple','output'):p.add_argument('--'+name,type=Path,required=True)
    main(p.parse_args())
