#!/usr/bin/env python3
"""Withdraw explicit shared source meanings found before native promotion.

This does not conflate time/weather or Chinese message/news. Existing bounded
sentence contexts remain; only the new unrestricted source units are withdrawn.
"""
import argparse
import json
from pathlib import Path
from authored_everyday import AUTHOR
from build_wiktextract import canonical, digest_file
from mapping_catalog import Catalog, digest

EXPORT_SHA = 'd60efa00e938942954d72a65d211fa8ec646bb4e83c9124ceac9afd380be7d30'


def selected(row):
    if not row['logical_id'].startswith('vipi-time-social-unit-r1:'):
        return False
    topic = row['logical_id'].split(':')[1]
    return ((row['source_language'] in ('es','fr','it','pt') and topic in ('time_duration','weather_conditions'))
            or (row['source_language'] == 'zh' and topic in ('message','news_information')))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--catalog', type=Path, required=True)
    p.add_argument('--receipt', type=Path, required=True)
    args = p.parse_args()
    if digest_file(args.input) != EXPORT_SHA or args.receipt.exists():
        raise ValueError('Pinned export and new receipt required')
    rows = [json.loads(line)['record'] for line in args.input.read_text().splitlines()]
    rows = [row for row in rows if selected(row)]
    assert len(rows) == 272
    evidence = [{'sha256':digest_file(Path(__file__)), 'description':'Explicit author withdrawal: time/weather share tiempo, temps or tempo; Chinese message/news share 消息. No context-free source sense choice approved.'},
        {'sha256':EXPORT_SHA, 'description':'Exact prior authored export; withdrawal applies only to the 272 listed new source units.'}]
    catalog = Catalog(args.catalog)
    try:
        for row in rows:
            catalog.review({'schema':'vipi-mapping-review-1', 'record_sha256':digest(row),
                'reviewer':AUTHOR, 'verdict':'quarantined', 'assessment_kind':'author_assessment',
                'evidence':evidence})
        receipt = {'schema':'vipi-time-social-withdrawal-1', 'records':len(rows), 'evidence':evidence,
            'record_sha256':[digest(row) for row in rows], 'ledger':catalog.stats(), 'release_ready':False}
        args.receipt.write_text(canonical(receipt)+'\n')
        print(canonical({k:v for k,v in receipt.items() if k!='record_sha256'}))
    finally:
        catalog.close()
