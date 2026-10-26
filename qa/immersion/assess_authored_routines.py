#!/usr/bin/env python3
"""Author assessment of the exact inspected routines batch, not future inputs.

The 210 authored language contexts have explicit lexical scopes. This does not
approve every provider translation or claim independent linguistic acceptance.
"""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'language-packs'))
from authored_everyday import AUTHOR
from mapping_catalog import Catalog,digest
from build_wiktextract import digest_file

EXPECTED='170021d6071e8bcecb17af7793301c6a7cd8b75884aee134e4d559aa3ddd11b0'


def main(a):
    if digest_file(a.records)!=EXPECTED:raise ValueError('Assessment only applies to inspected routines revision001')
    records=[json.loads(line) for line in a.records.read_text().splitlines()]
    if len(records)!=1890:raise ValueError('Unexpected batch size')
    evidence=[{'sha256':EXPECTED,'path':str(a.records),'description':'Author-inspected 21 meanings and ten direct language contexts per meaning, with explicit scopes and Latin readings'}]
    for path,platform in [(a.android,'Android'),(a.apple,'iOS')]:
        observed=json.loads(path.read_text())
        if observed.get('platform')!=platform or observed.get('cases')!=1890 or observed.get('reference_sha256')!=EXPECTED:
            raise ValueError('Wrong native reference evidence')
        if len(observed['results'])!=1890 or {r['case'] for r in observed['results']}!={r['logical_id'] for r in records}:
            raise ValueError('Incomplete native cases')
        evidence.append({'sha256':digest_file(path),'path':str(path),'description':'Native lexical-scope and mandatory-reading checks against retained actual provider output; authored development inputs'})
    a.output.mkdir(parents=True,exist_ok=False);catalog=Catalog(a.catalog)
    try:
        with (a.output/'assessments.jsonl').open('x') as stream:
            for record in records:
                report={'schema':'vipi-mapping-review-1','record_sha256':digest(record),'reviewer':AUTHOR,
                    'assessment_kind':'author_assessment','verdict':'reviewed','evidence':evidence,
                    'checks':{'meaning':'pass','usage':'pass','grammar_scope':'pass','provenance':'pass',
                        'reading':'pass' if record['target_language'] in ('ar','zh','ja','ko') else 'not_required'},
                    'rationale':'Author assessment of this exact context: '+record['meaning']+'. The ten references were inspected for their intended everyday sense and Latin reading. School, university, telephone, birthday and camera contexts constrain the relevant senses. Possessors, prepositions, articles and case particles remain outside lexical focus except established lexical compounds such as weekend and email. No arbitrary paraphrase or automatic stemming is authorized.',
                    'limits':['Author assessment, not an independent reviewer, fluency study or random conversation sample.',
                        'This assesses the authored lexical mapping, not every provider output or dialect.',
                        'Surface variants, loanword identity, ambiguous targets and reading guards can withhold immersion.',
                        'No general-chat, majority-coverage, release or subscription outcome claim.']}
                catalog.review(report);stream.write(json.dumps(report,ensure_ascii=False,sort_keys=True)+'\n')
        result={'reviewed':len(records),'assessment_kind':'author_assessment','records_sha256':EXPECTED,
            'assessments_sha256':digest_file(a.output/'assessments.jsonl'),'catalog':catalog.stats(),'release_ready':False}
        (a.output/'receipt.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
    finally:catalog.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('records','catalog','android','apple','output'):p.add_argument('--'+name,type=Path,required=True)
    main(p.parse_args())
