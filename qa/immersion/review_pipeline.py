#!/usr/bin/env python3
"""Summarize observed native outputs. Never assign semantic approval automatically."""
import argparse
import collections
import html
import json
from pathlib import Path
import statistics
import unicodedata


def utf16_slice(text, start, end):
    return text.encode('utf-16-le')[start * 2:end * 2].decode('utf-16-le')


def summarize(report):
    counts = collections.Counter()
    latency = []
    failures, empty_pairs, rows = [], [], []
    for pair in report['results']:
        pair_id = pair['source'] + '-' + pair['target']
        pair_spans = 0
        if pair.get('status') != 'executed':
            failures.append({'pair': pair_id, 'error': pair.get('error_type', 'not executed')})
        for sample in pair.get('samples', []):
            counts['samples'] += 1
            spans = sample.get('spans', [])
            counts['with_spans'] += bool(spans)
            counts['spans'] += len(spans)
            pair_spans += len(spans)
            if sample.get('status') != 'executed':
                failures.append({'pair': pair_id, 'case': sample['id'], 'error': sample.get('error_type', 'not executed')})
                continue
            latency.append(sample['lookup_alignment_ms'])
            cursor = 0
            for span in spans:
                assert span['start'] >= cursor, (pair_id, sample['id'], 'overlapping source ranges')
                assert utf16_slice(sample['original'], span['start'], span['end']) == span['original']
                assert utf16_slice(sample['translation'], span['targetStart'], span['targetEnd']) == span['translated']
                if pair['target'] in ('ar', 'zh', 'ja', 'ko'):
                    assert span.get('reading'), (pair_id, sample['id'], 'missing reading')
                cursor = span['end']
                if sample.get('reference'):
                    counts['reference_comparable_spans'] += 1
                    surface = unicodedata.normalize('NFC', span['translated']).casefold()
                    reference = unicodedata.normalize('NFC', sample['reference']).casefold()
                    counts['exact_surface_present_in_reference'] += surface in reference
            rows.append({'pair': pair_id, **sample})
        if not pair_spans:
            empty_pairs.append(pair_id)
    ordered = sorted(latency)
    return {'platform': report['platform'], 'evidence': report['evidence'],
            'review_label': report.get('review_label', report['platform']),
            'linguistic_acceptance': False, 'pairs': len(report['results']), **dict(counts),
            'reference_comparison_limit': 'Literal normalized surface occurrence only; not alignment, semantic accuracy or reading validation.',
            'zero_span_pairs': empty_pairs, 'execution_failures': failures,
            'lookup_alignment_ms': {'median': statistics.median(ordered) if ordered else None,
                                    'p95': ordered[min(len(ordered) - 1, int(len(ordered) * .95))] if ordered else None}}, rows


def main(args):
    output = args.output
    output.mkdir(parents=True, exist_ok=False)
    reports = [json.loads(path.read_text()) for path in args.report]
    if args.label:
        if len(args.label) != len(reports):
            raise ValueError('Supply one label for each report')
        for report, label in zip(reports, args.label): report['review_label'] = label
    summaries, datasets = zip(*(summarize(report) for report in reports))
    indexed = [{(row['pair'], row['id']): row for row in rows} for rows in datasets]
    differences = []
    if len(indexed) == 2:
        for key in sorted(indexed[0].keys() & indexed[1].keys()):
            if indexed[0][key]['spans'] != indexed[1][key]['spans']:
                differences.append({'pair': key[0], 'case': key[1]})
    receipt = {'quality': 'engineering_observation_pending_semantic_review',
               'linguistic_acceptance': False, 'reports': summaries, 'span_differences': differences}
    (output / 'summary.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    rows = []
    for summary, samples in zip(summaries, datasets):
        for sample in samples:
            replacements = ' · '.join(f"{s['original']} → " + (f"{s['reading']} ({s['translated']})" if s['reading'] else s['translated']) for s in sample['spans']) or 'No replacement: original retained'
            rows.append('<tr data-pair="' + sample['pair'] + '"><td>' + html.escape(summary['review_label']) + '</td><td>' + sample['pair'] + '<br>' + sample['id'] + '</td><td dir="auto">' + html.escape(sample['original']) + '</td><td dir="auto">' + html.escape(sample['translation']) + '</td><td dir="auto">' + html.escape(sample.get('reference') or 'Not supplied in this receipt') + '</td><td dir="auto">' + html.escape(replacements) + '</td></tr>')
    pairs = sorted({row['pair'] for samples in datasets for row in samples})
    credits = ['Dictionary candidates: Wiktionary contributors, via Wiktextract/Kaikki; CC-BY-SA-4.0.']
    for report in reports:
        attribution = report.get('attribution')
        if attribution:
            credits.append('Reference corpus: ' + attribution['name'] + '; ' + attribution['license'] + '. ' + attribution['url'])
    attribution_html = ''.join('<p>' + html.escape(credit) + '</p>' for credit in dict.fromkeys(credits))
    page = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Vipi — observed local immersion</title><style>body{font:16px system-ui;margin:24px;color:#142c29;background:#f7f8f4}h1{font-size:28px}p{max-width:80ch;line-height:1.5}select{font:inherit;padding:8px}table{border-collapse:collapse;width:100%;margin-top:20px}th,td{padding:12px;border-bottom:1px solid #cbd8d2;text-align:start;vertical-align:top}th{position:sticky;top:0;background:#e5eee7}td{min-width:100px}td:nth-child(n+3){min-width:220px}.scroll{overflow:auto}tr[hidden]{display:none}</style><h1>Observed local immersion</h1><p>Actual offline ML Kit translations with signed dictionary candidates. The iOS results use the same captured translations with Apple's native tokenization and alignment; they do not demonstrate Apple translation. This review exposes every replacement, including omissions. It is not linguistic approval, an app screenshot, or a user study.</p><label>Language direction <select id="pair"><option value="">All directions</option>''' + ''.join('<option>' + pair + '</option>' for pair in pairs) + '''</select></label><div class="scroll"><table><thead><tr><th>Platform</th><th>Case</th><th>Original</th><th>Actual translation</th><th>Selected vocabulary</th></tr></thead><tbody>''' + ''.join(rows) + '''</tbody></table></div><script>document.querySelector('#pair').addEventListener('change',event=>document.querySelectorAll('tbody tr').forEach(row=>row.hidden=!!event.target.value&&row.dataset.pair!==event.target.value));</script></html>'''
    page = page.replace('<th>Selected vocabulary</th>', '<th>Independent reference</th><th>Selected vocabulary</th>')
    page = page.replace('<script>', '<p>Reference surface occurrence is a literal text comparison, not semantic accuracy, alignment or pronunciation validation. The independent reference corpus uses formal prose, not chat.</p>' + attribution_html + '<script>')
    (output / 'review.html').write_text(page)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', action='append', type=Path, required=True)
    parser.add_argument('--label', action='append', default=[])
    parser.add_argument('--output', type=Path, required=True)
    main(parser.parse_args())
