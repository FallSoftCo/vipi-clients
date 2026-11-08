#!/usr/bin/env python3
"""Paired target transfer; unchanged Latin spellings earn no immersion credit."""
import argparse
import copy
import json
from pathlib import Path
import statistics
import time
import unicodedata

from evaluate_source_concepts import candidates, evaluate, sha


def normalized(value):
    return unicodedata.normalize('NFKC', value).casefold()


def changed_lexicon(lexicon):
    return dict(lexicon, entries=[e for e in lexicon['entries']
        if normalized(e['source']) != normalized(e['target'])])


def main():
    parser = argparse.ArgumentParser()
    for key in ('protocol', 'lexicon', 'control', 'rules', 'freeze', 'output'):
        parser.add_argument('--'+key, type=Path, required=True)
    args = parser.parse_args()
    started = time.perf_counter_ns()
    protocol, lexicon, control, rules, freeze = [json.loads(getattr(args,key).read_text())
        for key in ('protocol','lexicon','control','rules','freeze')]
    assert sha(args.protocol) == freeze['paired_protocol_sha256']
    for key in ('lexicon','control','rules'):
        assert sha(getattr(args,key)) == freeze[key+'_sha256']
    assert sha(Path(__file__)) == freeze['evaluator_sha256']
    assert sha(Path(__file__).with_name('evaluate_source_concepts.py')) == freeze['source_evaluator_sha256']
    changed = changed_lexicon(lexicon)
    old = changed_lexicon(control)
    equal = dict(lexicon, entries=[e for e in lexicon['entries'] if e not in changed['entries']])
    changed_rules = copy.deepcopy(rules)
    for group in ('single_words','units'):
        changed_rules[group] = {source:rule for source,rule in rules[group].items()
            if normalized(source) != normalized(rule['target'])}
    init_ms = (time.perf_counter_ns()-started)/1e6
    rows, times = [], []
    for original_case in protocol['cases']:
        assert original_case['source'] == 'en'
        case = dict(original_case, target='es')
        started = time.perf_counter_ns()
        row = evaluate(case, changed, old, changed_rules)
        _, unchanged, _ = candidates(case['text'], equal)
        row['rejections'] += [dict(span, reason='unchanged_face') for span in unchanged]
        for spans in [row['candidates'], row['rejections']] + [a['spans'] for a in row['arms'].values()]:
            for span in spans:
                span['lexicon_id'] = span['lexicon_id'].replace('question-en-sw-', 'question-en-es-')
        assert all(normalized(s['original']) != normalized(s['translated'])
            for a in row['arms'].values() for s in a['spans'])
        times.append((time.perf_counter_ns()-started)/1e6)
        rows.append(row)
    result = dict(schema='vipi-spanish-source-transfer-evaluation-1', production=False, provider_calls=0,
        control_description='First100 source forms transferred to Spanish with the same target-specific exclusions; not current native production runtime.',
        source_sample='Exact frozen Japanese source sample, target tag changed to es only; Spanish targets and wrapper frozen before root opened any source cases.',
        input_hashes={key:sha(getattr(args,key)) for key in ('protocol','lexicon','control','rules','freeze')},
        semantic_review='pending', native_qualification=False,
        unchanged_face_policy='NFKC+casefold equal forms excluded from candidate/control before selection and retained as unchanged_face rejections.',
        timing=dict(environment='Existing system76 Python CPU; not mobile', initialization_ms=init_ms,
            median_all_arms_ms=statistics.median(times),p95_all_arms_ms=sorted(times)[int(.95*len(times))-1]),
        summaries={arm:dict(messages_with_span=sum(bool(row['arms'][arm]['spans']) for row in rows),
            mean_changed_depth=statistics.mean(row['arms'][arm]['changed_depth'] for row in rows)) for arm in rows[0]['arms']}, rows=rows)
    assert not args.output.exists(), 'Retain original evaluation; use a new output for a new run.'
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('summaries','timing')},indent=2))


if __name__ == '__main__':
    main()
