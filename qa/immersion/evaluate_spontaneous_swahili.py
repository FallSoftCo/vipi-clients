#!/usr/bin/env python3
"""Count actual conversation-path availability without inventing meaning labels."""
import argparse
from collections import Counter
import json
from pathlib import Path
import statistics
from conversation_corpus import sha_file, write_json
from review_pipeline import utf16_slice


def summarize(report, corpus):
    if report['schema'] != 'vipi-spontaneous-swahili-coverage-1' or corpus['schema'] != 'vipi-liva-swahili-probe-1':
        raise ValueError('Wrong evidence schema')
    expected = {(r['id'], target):r['text']['sw'] for r in corpus['cases'] for target in corpus['targets']}
    counts = {mode:{target:Counter() for target in corpus['targets']} for mode in ['automatic','explicit_sw']}
    latency = {mode:[] for mode in counts}; covered = {mode:set() for mode in counts}; seen = set()
    for row in report['rows']:
        identity = row['id'],row['target']
        if identity in seen or identity not in expected or row['source'] != 'sw' or row['original'] != expected[identity]:
            raise ValueError('Changed or duplicated case')
        seen.add(identity)
        for mode in counts:
            result = row[mode]; count = counts[mode][row['target']]; count['cases'] += 1
            latency[mode].append(row['automatic_elapsed_ms' if mode == 'automatic' else 'explicit_elapsed_ms'])
            if result is None: count['no_prepared_output'] += 1; continue
            if mode == 'explicit_sw' and result['baseline'] != row['original']: raise ValueError('Changed explicit baseline')
            if row['original'] not in (result['baseline'],result['translation']): raise ValueError('Lost sender text')
            count['prepared_output'] += 1
            count['reverse_input'] += result['baseline'] != row['original']
            count['with_immersion'] += bool(result['spans']); count['spans'] += len(result['spans'])
            if result['spans']: covered[mode].add(row['id'])
            end = 0
            for span in result['spans']:
                if span['start'] < end or span['end'] <= span['start']: raise ValueError('Overlapping or empty source scope')
                if utf16_slice(result['baseline'],span['start'],span['end']) != span['original']: raise ValueError('Changed source scope')
                if utf16_slice(result['translation'],span['targetStart'],span['targetEnd']) != span['translated']: raise ValueError('Changed target scope')
                if row['target'] in ['ar','zh','ja','ko'] and not span['reading']: raise ValueError('Missing reading')
                end = span['end']
    if seen != set(expected): raise ValueError('Incomplete report')
    result = {'source_turns':len(corpus['cases']), 'conversations':len({r['conversation'] for r in corpus['cases']}), 'directions':len(corpus['targets'])}
    for mode, pairs in counts.items():
        total = Counter()
        for values in pairs.values(): total.update(values)
        result[mode] = {'pairs':{target:dict(values) for target,values in pairs.items()}, 'totals':dict(total),
            'distinct_turns_with_immersion':len(covered[mode]), 'message_availability':total['with_immersion']/total['cases'],
            'latency_ms':{'median':statistics.median(latency[mode]), 'p95':sorted(latency[mode])[int(len(latency[mode])*.95)]}}
    return result


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['report','corpus','catalog','output']: parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args(); report=json.loads(args.report.read_text()); corpus=json.loads(args.corpus.read_text())
    if report['corpus_sha256'] != sha_file(args.corpus) or report['catalog_sha256'] != sha_file(args.catalog):
        raise ValueError('Changed corpus or app catalog')
    if args.output.exists(): raise ValueError('Preserve earlier receipt')
    result = {'schema':'vipi-spontaneous-swahili-summary-1', 'platform':report['platform'],
        'corpus_sha256':sha_file(args.corpus), 'report_sha256':sha_file(args.report), 'catalog_sha256':sha_file(args.catalog),
        'evaluator_sha256':sha_file(Path(__file__)), 'semantic_accuracy':None, 'independent_linguistic_acceptance':False,
        'limits':corpus['limits'], **summarize(report,corpus)}
    write_json(args.output,result)
    print(json.dumps({k:v for k,v in result.items() if k not in ['automatic','explicit_sw']} | {
        mode:{k:v for k,v in result[mode].items() if k != 'pairs'} for mode in ['automatic','explicit_sw']}))
