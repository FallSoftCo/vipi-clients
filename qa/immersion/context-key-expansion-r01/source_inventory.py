#!/usr/bin/env python3
"""Count source-only context reach before any new translation extraction.

Reads the exact retained 40k Tatoeba development pairs and native TRAIN windows.
No target text, alignment, dictionary, translation provider or output labels are
used. This is a lookup ceiling, not an estimate of correct immersion coverage.
"""
import argparse
import ast
import bisect
import collections
import gzip
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import time
import unicodedata


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1048576), b''):
            h.update(chunk)
    return h.hexdigest()


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('protocol', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    started = time.monotonic()
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    os.nice(10)
    resource.setrlimit(resource.RLIMIT_AS, (1024**3,) * 2)
    def timeout(*unused):
        raise TimeoutError('300 second source-inventory limit')
    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(300)
    plan = json.loads(args.protocol.read_text())
    assert plan['script_sha256'] == sha(Path(__file__))
    assert shutil.disk_usage(args.output.parent).free >= 1024**3 + 64*1024**2
    paths = {}
    for name, binding in plan['inputs'].items():
        path = Path(binding['path'])
        assert path.is_file() and sha(path) == binding['sha256'], name
        paths[name] = path
    args.output.mkdir(exist_ok=False)
    receipt = {'complete': False, 'production': False,
               'protocol_sha256': sha(args.protocol), 'target_text_used': False}
    try:
        # Load only the two unchanged pure source functions, never old drivers.
        env = {'unicodedata': unicodedata}
        for key, name in [('normalizer', 'norm'), ('phrase_helper', 'crosses_stop')]:
            tree = ast.parse(paths[key].read_text())
            if key == 'phrase_helper':
                node = next(n for n in tree.body if isinstance(n, ast.Assign)
                            and any(isinstance(t, ast.Name) and t.id == 'STOPS' for t in n.targets))
                env['STOPS'] = ast.literal_eval(node.value)
            node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
            exec(compile(ast.Module(body=[node], type_ignores=[]), str(paths[key]), 'exec'), env)
        norm, crosses = env['norm'], env['crosses_stop']
        frequency = json.loads(paths['fixed_keys'].read_text())
        fixed = {r['source_key'] for r in frequency['unigram_keys'] + frequency['multiword_keys']}
        assert len(fixed) == 8000 and len(frequency['unigram_keys']) == 3000
        corpus = collections.Counter()
        sentence_support = collections.Counter()
        lengths = collections.defaultdict(set)
        corpus_rows = 0
        with gzip.open(paths['pairs'], 'rt') as stream:
            for line in stream:
                row = json.loads(line)
                assert row['index'] == corpus_rows and row['pair'] == 'en-es'
                source = row['source']
                tokens = source['tokens']
                words = [t['text'].casefold() for t in tokens]
                seen = set()
                for left in range(len(tokens)):
                    for right in range(left + 1, min(left + 8, len(tokens)) + 1):
                        if crosses(words[left:right]):
                            break
                        a, b = tokens[left]['codepoints'][0], tokens[right - 1]['codepoints'][1]
                        key = norm(source['text'][a:b])
                        if right - left == 1 and key not in fixed:
                            continue
                        corpus[key] += 1
                        lengths[key].add(right - left)
                        seen.add(key)
                sentence_support.update(seen)
                corpus_rows += 1
        assert corpus_rows == 40000
        matched = collections.Counter()
        native_lengths = collections.defaultdict(set)
        message_metrics = collections.Counter()
        buckets = {name: collections.Counter() for name in ['fixed', 'expanded', 'new']}
        rows = 0
        # Retain per-message counts only, never source or translated sentences.
        with (args.output / 'messages.jsonl').open('x') as output:
            for line in paths['geometry'].open():
                row = json.loads(line)
                raw = row['text'].encode('utf-16-le')
                words = row['native_source_word_ranges_utf16']
                starts, ends = [w[0] for w in words], [w[1] for w in words]
                keys = set()
                row_lengths = collections.defaultdict(set)
                for left, right in row['native_window_ranges_utf16']:
                    key = norm(raw[2*left:2*right].decode('utf-16-le'))
                    if key not in corpus:
                        continue
                    cost = bisect.bisect_right(ends, right) - bisect.bisect_left(starts, left)
                    assert 1 <= cost <= 8
                    if cost == 1 and key not in fixed:
                        continue
                    keys.add(key)
                    native_lengths[key].add(cost)
                    row_lengths[key].add(cost)
                matched.update(keys)
                fixed_hits, new_hits = keys & fixed, keys - fixed
                groups = {'fixed': fixed_hits, 'expanded': keys, 'new': new_hits}
                for name, found in groups.items():
                    if found:
                        message_metrics[name + '_any'] += 1
                    for low, high in [(2, 3), (4, 8)]:
                        if any(any(low <= n <= high for n in row_lengths[k]) for k in found):
                            buckets[name][f'{low}-{high}'] += 1
                message_metrics['new_keys_without_prior_any'] += bool(new_hits and not fixed_hits)
                output.write(json.dumps({'id': row['id'], 'fixed_keys': len(fixed_hits),
                                         'new_keys': len(new_hits)}) + '\n')
                rows += 1
        assert rows == 9535
        inventory = [{'source_key': key, 'fixed': key in fixed,
                      'native_word_costs': sorted(native_lengths[key]),
                      'corpus_token_counts': sorted(lengths[key]),
                      'corpus_occurrences': corpus[key],
                      'corpus_sentence_pairs': sentence_support[key],
                      'native_messages': matched[key]} for key in sorted(matched)]
        with gzip.open(args.output / 'matched-keys.json.gz', 'xt') as stream:
            json.dump(inventory, stream, ensure_ascii=False, separators=(',', ':'))
        receipt.update(complete=True, corpus_pairs=corpus_rows, native_messages=rows,
                       source_inventory_keys=len(corpus), fixed_source_keys_present=len(set(corpus) & fixed),
                       matched_keys=len(matched), new_matched_keys=len(set(matched) - fixed),
                       native_message_counts=dict(message_metrics),
                       native_message_length_buckets={k: dict(v) for k, v in buckets.items()},
                       limit='Exact source-match ceiling only; no target alignment, head, role, budget or meaning acceptance. Reused TRAIN, not population/holdout.')
    except BaseException as exc:
        receipt['error'] = repr(exc)
        raise
    finally:
        process_memory = {key: int(value.split()[0]) * 1024
                          for key, value in (line.split(':', 1)
                              for line in Path('/proc/self/status').read_text().splitlines()
                              if line.startswith(('VmHWM:', 'VmPeak:', 'VmRSS:')))}
        receipt.update(seconds=time.monotonic() - started,
                       process_memory_bytes=process_memory,
                       outputs={p.name: {'bytes': p.stat().st_size, 'sha256': sha(p)}
                                for p in args.output.iterdir() if p.is_file()})
        assert sum(v['bytes'] for v in receipt['outputs'].values()) <= 64*1024**2
        write(args.output / 'receipt.json', receipt)
        print(json.dumps(receipt, sort_keys=True))


if __name__ == '__main__':
    main()
