#!/usr/bin/env python3
"""Import an explicitly assessed authored batch; never infer an assessment.

The human-readable assessment must name the exact records and authoring source.
Existing immutable revisions and checkpoints make a completed repeat idempotent.
"""
import argparse
import json
from pathlib import Path
from authored_everyday import AUTHOR
from build_wiktextract import canonical, digest_file
from mapping_catalog import Catalog, digest, import_records
from export_reviewed_frames import compile_record as compile_frame
from export_reviewed_contexts import compile_record as compile_context

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--catalog', type=Path, required=True)
    p.add_argument('--records', type=Path, required=True)
    p.add_argument('--assessment', type=Path, required=True)
    p.add_argument('--authoring-source', type=Path, required=True)
    p.add_argument('--receipt', type=Path, required=True)
    p.add_argument('--kind', choices=['frames', 'contexts'], default='frames')
    a = p.parse_args()
    assessment = json.loads(a.assessment.read_text())
    if assessment['records_sha256'] != digest_file(a.records) or assessment['authoring_source_sha256'] != digest_file(a.authoring_source):
        raise ValueError('Assessment does not bind this batch and source')
    if assessment['assessment_kind'] != 'author_assessment' or assessment['reviewer'] != AUTHOR:
        raise ValueError('An explicit author assessment is required')
    rows = [json.loads(line) for line in a.records.read_text().splitlines()]
    if len(rows) != assessment['records']: raise ValueError('Wrong record count')
    reviews = []
    for row in rows:
        review = {'schema':'vipi-mapping-review-1', 'record_sha256':digest(row), 'reviewer':AUTHOR,
            'verdict':'reviewed', 'assessment_kind':'author_assessment',
            'checks':dict(assessment['checks'], reading='pass' if row['target_language'] in ('ar','zh','ja','ko') else 'not_required'),
            'evidence':[{'sha256':digest_file(a.assessment), 'description':'Explicit content-bound author assessment; not independent acceptance'},
                        {'sha256':digest_file(a.records), 'description':'Exact authored development batch'}]}
        compiler = compile_frame if a.kind == 'frames' else compile_context
        compiler({'record':row, 'sha256':digest(row), 'assessments':[review]})
        reviews.append(review)
    catalog = Catalog(a.catalog)
    try:
        import_records(catalog, a.records, 500, None)
        for review in reviews: catalog.review(review)
        receipt = {'records_sha256':digest_file(a.records), 'assessment_sha256':digest_file(a.assessment),
            'assessed_records':len(reviews), 'ledger':catalog.stats(), 'release_ready':False}
        with a.receipt.open('x') as out: out.write(canonical(receipt)+'\n')
        print(canonical(receipt))
    finally: catalog.close()

if __name__ == '__main__': main()
