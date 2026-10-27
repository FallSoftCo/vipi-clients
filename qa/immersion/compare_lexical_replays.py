#!/usr/bin/env python3
"""Expose additions and losses between captured native runs for author review."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def identity(row):
    return tuple(row[k] for k in ('dataset', 'id', 'source', 'target'))


def main(args):
    manifest = json.loads((args.fixture / 'manifest.json').read_text())
    assert sha(args.fixture / 'cases.json') == manifest['cases_sha256']
    cases = {identity(r): r for r in json.loads((args.fixture / 'cases.json').read_text())}
    before, after = (json.loads(p.read_text()) for p in (args.base_report, args.report))
    assert before['complete'] and after['complete'] and before['platform'] == after['platform']
    assert after['manifest_sha256'] == sha(args.fixture / 'manifest.json')
    old = {identity(r): r for r in before['outcomes']}
    new = {identity(r): r for r in after['outcomes']}
    assert set(new) == set(cases) and len(new) == manifest['cases']
    changes, watches, counts = [], [], Counter()
    def encoded(span):
        return json.dumps(span, ensure_ascii=False, sort_keys=True)
    for key in sorted(set(old) & set(new)):
        left, right = old[key]['combined_spans'], new[key]['combined_spans']
        added = [s for s in right if encoded(s) not in {encoded(x) for x in left}]
        removed = [s for s in left if encoded(s) not in {encoded(x) for x in right}]
        if added or removed:
            counts['changed_messages'] += 1
            counts['added_spans'] += len(added)
            counts['removed_spans'] += len(removed)
            counts['newly_nonempty_messages'] += int(not left and bool(right))
            counts['newly_empty_messages'] += int(bool(left) and not right)
            changes.append(dict(identity=key, original=cases[key]['original'], translation=cases[key]['translation'], added=added, removed=removed))
        if 'availability_watch' in cases[key]:
            watch = cases[key]['availability_watch']
            def present(spans):
                return any(s['source'] == watch['source'] and s['target'] == watch['target'] for s in spans)
            watches.append(dict(identity=key, watch=watch, base_present=present(left), current_present=present(right)))
    result = dict(schema='vipi-lexical-replay-changes-1', base_sha256=sha(args.base_report), report_sha256=sha(args.report),
                  platform=after['platform'], base=before['run'], revision=after['run'], compared_cases=len(set(old) & set(new)),
                  new_cases=len(set(new) - set(old)), omitted_base_cases=len(set(old) - set(new)), counts=dict(counts),
                  changes=changes, availability_watches=watches, independent_semantic_acceptance=False)
    with args.output.open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'changes'}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('fixture', 'base-report', 'report', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    main(parser.parse_args())
