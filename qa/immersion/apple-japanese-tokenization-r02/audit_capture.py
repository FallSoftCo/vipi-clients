"""Independently verify a frozen native Japanese geometry capture (no provider calls)."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import statistics
import unicodedata


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def utf16len(text):
    return len(text.encode('utf-16-le')) // 2


def audit(inputs_path, capture_path, baseline_path):
    inputs = json.loads(Path(inputs_path).read_text())['cases']
    rows = [json.loads(line) for line in Path(capture_path).read_text().splitlines()]
    baseline = [json.loads(line) for line in Path(baseline_path).read_text().splitlines()]
    assert [r['id'] for r in rows] == [r['id'] for r in inputs] == [r['id'] for r in baseline]
    summaries = []
    for row, source, previous in zip(rows, inputs, baseline):
        text = source['text']
        assert row['text'].encode() == text.encode()
        assert hashlib.sha256(text.encode()).hexdigest() == source['original_sha256'] == row['original_sha256']
        geometry = row['first']
        assert row['warm_equal']
        assert geometry['raw_native_words'] == previous['first']['raw_native_words']
        assert geometry['protected_ranges'] == previous['first']['protected_ranges']
        if geometry['status'] == 'input_length_rejected':
            assert utf16len(text) > 16384 or not text
            assert not geometry['tokens'] and not geometry['separators'] and not geometry['raw_native_words']
            summaries.append({'id': row['id'], 'status': geometry['status']})
            continue
        assert geometry['status'] == 'tokenized' and geometry['exact_reconstruction']
        def check(piece):
            start, end = piece['codepoints']
            assert 0 <= start < end <= len(text)
            assert piece['text'].encode() == text[start:end].encode()
            assert piece['utf16'] == [utf16len(text[:start]), utf16len(text[:end])]
        for p in geometry['raw_native_words'] + geometry['tokens'] + geometry['separators']:
            check(p)
        partition = sorted(geometry['tokens'] + geometry['separators'], key=lambda p: p['codepoints'][0])
        position = 0
        for p in partition:
            assert p['codepoints'][0] == position
            assert p['grapheme_aligned']
            position = p['codepoints'][1]
        assert position == len(text) and ''.join(p['text'] for p in partition).encode() == text.encode()
        assert all(p['kind'] == 'separator' and p['text'].isspace() for p in geometry['separators'])
        literals = geometry['protected_ranges']
        assert literals == [p for p in geometry['tokens'] if p['kind'] == 'literal']
        for p in geometry['tokens']:
            assert p['kind'] in {'word', 'punctuation', 'symbol', 'other', 'literal'}
            if p['kind'] != 'literal':
                assert not p['text'].isspace()
                assert not any(max(p['utf16'][0], q['utf16'][0]) < min(p['utf16'][1], q['utf16'][1]) for q in literals)
            if p['kind'] == 'word':
                assert any(unicodedata.category(c)[0] == 'L' or unicodedata.category(c) == 'Nd' for c in p['text'])
            if p['kind'] == 'symbol':
                assert any(unicodedata.category(c)[0] == 'S' for c in p['text'])
            if p['kind'] == 'punctuation':
                assert all(unicodedata.category(c)[0] == 'P' for c in p['text'])
        summaries.append({'id': row['id'], 'status': geometry['status'], 'tokens': len(geometry['tokens']),
                          'raw_native_words': len(geometry['raw_native_words']), 'protected_ranges': len(literals),
                          'diagnostics': geometry['diagnostics'], 'exact_partition': True})
    return {'schema': 'vipi.japanese-tokenization-independent-audit.1', 'inputs_sha256': sha(inputs_path),
            'capture_sha256': sha(capture_path), 'baseline_capture_sha256': sha(baseline_path),
            'rows': len(rows), 'statuses': dict(collections.Counter(r['first']['status'] for r in rows)),
            'warm_equal_rows': sum(r['warm_equal'] for r in rows), 'raw_native_and_literal_ranges_unchanged': True,
            'first_median_ms': statistics.median(r['first_milliseconds'] for r in rows),
            'warm_median_ms': statistics.median(r['warm_milliseconds'] for r in rows),
            'first_max_ms': max(r['first_milliseconds'] for r in rows),
            'peak_rss_bytes': max(r['peak_rss_bytes'] for r in rows), 'cases': summaries}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('inputs'); parser.add_argument('capture'); parser.add_argument('baseline'); parser.add_argument('output')
    args = parser.parse_args()
    result = audit(args.inputs, args.capture, args.baseline)
    with Path(args.output).open('x') as file:
        json.dump(result, file, ensure_ascii=False, indent=2); file.write('\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'cases'}, indent=2))
