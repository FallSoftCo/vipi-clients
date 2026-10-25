#!/usr/bin/env python3
"""Combine native lexical gates with contextual alignment for review only.

This uses captured provider translations, not authored target sentences. The
native export retains ambiguity, conflicting-cue, grammar, protected-text and
reading checks. Only its positive sentence-cue requirement is relaxed for this
probe. No output from this script is displayed by the application.
"""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import time

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def cp_offset(text, offset):
    return len(text.encode('utf-16-le')[:offset * 2].decode('utf-16-le'))


def main(args):
    data = json.loads(args.native.read_text())
    policy = 'native-lexical-ambiguity-reading-protection-cue-veto-without-positive-cue-requirement-1'
    assert data['context_candidate_policy'] == policy
    assert data['network_absence_verified'] is True
    assert len(data['results']) == 90
    args.output.mkdir(parents=True, exist_ok=False)
    model = args.model / 'onnx/model_qint8_avx512_vnni.onnx'
    vocabulary = args.model / 'onnx/tokenizer.json'
    protocol = {
        'schema': 1, 'model': 'multilingual-e5-small pinned qualification weights',
        'native_candidate_policy': policy,
        'selection': 'One exact native word on each side; mutual top-one cosine over all native words; no fitted threshold',
        'presentation_budget': 'At most floor(0.3 * source native words), at least one; native candidate order retained',
        'scope': '540 reused development messages and captured actual ML Kit outputs; not held-out acceptance',
        'semantic_approval': False, 'mobile_qualification': False,
        'source_hashes': {str(p): sha(p) for p in [Path(__file__), args.native, model, vocabulary]},
    }
    raw = (json.dumps(protocol, indent=2) + '\n').encode()
    (args.output / 'protocol.json').write_bytes(raw)
    options = ort.SessionOptions(); options.intra_op_num_threads = 2; options.inter_op_num_threads = 1
    started = time.perf_counter()
    runtime = ort.InferenceSession(str(model), sess_options=options, providers=['CPUExecutionProvider'])
    tokenizer = Tokenizer.from_file(str(vocabulary)); tokenizer.no_padding(); tokenizer.no_truncation()
    names = {v.name for v in runtime.get_inputs()}
    load_ms = (time.perf_counter() - started) * 1000
    cache, times = {}, []
    prefix = 'query: '

    def vectors(text, words):
        key = text, tuple((w['start'], w['end']) for w in words)
        if key in cache:
            return cache[key]
        before = time.perf_counter()
        encoding = tokenizer.encode(prefix + text)
        assert len(encoding.ids) <= 512, 'No silently truncated context'
        feeds = {'input_ids': np.array([encoding.ids], dtype=np.int64),
                 'attention_mask': np.array([encoding.attention_mask], dtype=np.int64),
                 'token_type_ids': np.array([encoding.type_ids], dtype=np.int64)}
        hidden = runtime.run(None, {k: v for k, v in feeds.items() if k in names})[0][0]
        pooled = []
        for word in words:
            start, end = cp_offset(text, word['start']), cp_offset(text, word['end'])
            assert text[start:end] == word['text']
            indices = [i for i, (a, b) in enumerate(encoding.offsets)
                       if not encoding.special_tokens_mask[i] and a < end + len(prefix) and b > start + len(prefix)]
            assert indices
            value = hidden[indices].mean(axis=0)
            norm = np.linalg.norm(value); assert np.isfinite(norm) and norm > 0
            pooled.append(value / norm)
        result = np.array(pooled)
        cache[key] = result; times.append((time.perf_counter() - before) * 1000)
        return result

    rows = []
    totals = dict(messages=0, native_candidates=0, single_word_candidates=0,
                  corroborated_candidates=0, selected=0, messages_with_spans=0, strict_native_spans=0)
    empty = []
    for pair in data['results']:
        assert pair['status'] == 'executed'
        samples = []; pair_selected = 0
        for sample in pair['samples']:
            assert sample['status'] == 'executed'
            left, right = sample['source_words'], sample['target_words']
            candidates = sample['context_candidates']
            totals['messages'] += 1; totals['native_candidates'] += len(candidates)
            totals['strict_native_spans'] += len(sample['spans'])
            observations, selected = [], []
            if left and right and candidates:
                similarities = vectors(sample['original'], left) @ vectors(sample['translation'], right).T
                for candidate in candidates:
                    a = [i for i, w in enumerate(left) if (w['start'], w['end']) == (candidate['start'], candidate['end'])]
                    b = [i for i, w in enumerate(right) if (w['start'], w['end']) == (candidate['targetStart'], candidate['targetEnd'])]
                    if len(a) != 1 or len(b) != 1:
                        observations.append({**candidate, 'corroborated': False, 'reason': 'not_exact_single_native_words'})
                        continue
                    i, j = a[0], b[0]; totals['single_word_candidates'] += 1
                    mutual = int(similarities[i].argmax()) == j and int(similarities[:, j].argmax()) == i
                    observation = {**candidate, 'corroborated': mutual, 'cosine': float(similarities[i, j])}
                    observations.append(observation)
                    if mutual:
                        selected.append(candidate); totals['corroborated_candidates'] += 1
            selected = selected[:max(1, int(len(left) * .3))]
            totals['selected'] += len(selected); totals['messages_with_spans'] += bool(selected); pair_selected += len(selected)
            samples.append({'id': sample['id'], 'original': sample['original'], 'translation': sample['translation'],
                            'reference': sample.get('reference'), 'spans': selected, 'candidates': observations,
                            'strict_native_spans': sample['spans']})
        rows.append({'source': pair['source'], 'target': pair['target'], 'samples': samples})
        if not pair_selected:
            empty.append(pair['source'] + '-' + pair['target'])
    report = {'protocol_sha256': hashlib.sha256(raw).hexdigest(), **totals, 'zero_span_pairs': empty,
              'load_ms': load_ms, 'unique_encoded_sentences': len(times),
              'sentence_p50_ms': float(np.median(times)), 'sentence_p95_ms': float(np.percentile(times, 95)),
              'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
              'platform': 'OZZZ-OS CPU, two inference threads; not mobile latency',
              'linguistic_acceptance': False, 'results': rows}
    (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'results'}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ['native', 'model', 'output']:
        parser.add_argument('--' + option, type=Path, required=True)
    main(parser.parse_args())
