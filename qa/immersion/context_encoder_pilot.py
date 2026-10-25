#!/usr/bin/env python3
"""Falsification probe, authored English examples; not semantic acceptance.

Protocol is fixed before inference. Rank all labels from the existing en-es
pack using E5 query(sentence + focused word) versus passage(word + gloss).
Abstain below a 0.02 top-two cosine margin. A margin is not a probability.
No native integration, network inference, or threshold fitting is performed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import sqlite3
import time

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

CASES = [
    ('bank', 'We sat on the bank and watched the ducks swim past.', ['edge of river or lake']),
    ('bank', 'I need to visit the bank to deposit a cheque.', ['institution', 'branch office', 'to deal with a bank or financial institution']),
    ('bank', 'The pilot began to bank left as the runway came into view.', ['to make incline in turn', 'to incline laterally in order to turn']),
    ('period', 'The dot at the end of this sentence is a period.', ['punctation mark “.”']),
    ('period', 'Several atoms could fit inside a printed period.', ['punctation mark “.”']),
    ('period', 'We lived there for a short period before moving home.', ['interval of time']),
    ('period', 'Each period in the table contains elements in a horizontal row.', ['chemistry: row in the periodic table']),
    ('period', 'Our maths lesson is in the first period after lunch.', ['division of school day']),
    ('coffee', 'Would you like a coffee while we wait?', ['beverage']),
    ('coffee', 'Please bring me a hot coffee with milk.', ['beverage']),
    ('coffee', 'They grow coffee on the hillside behind the house.', ['plant']),
    ('coffee', 'Grind the coffee just before brewing.', ['beans']),
    ('light', 'This bag is light enough to carry with one hand.', ['of low weight']),
    ('light', 'Switch on the light so we can see the map.', ['source of illumination']),
    ('light', 'Can you light the candle for me?', ['to set fire to', 'to start (a fire)']),
    ('book', 'I want to book a table for two tonight.', ['to reserve']),
    ('book', 'She opened her book and read the first page.', ['collection of sheets of paper bound together containing printed or written material']),
    ('match', 'We watched the football match together last night.', ['sporting event']),
    ('match', 'Strike a match to light the candle.', ['device to make fire']),
    ('charge', 'How much do they charge for delivery?', ['to demand, require payment']),
    ('charge', 'I need to charge my phone before we leave.', ['to add energy to']),
    ('fit', 'These shoes fit my feet perfectly.', ['to conform to in size and shape', 'to have right size and shape']),
    ('fit', 'Regular running keeps her fit.', ['in good shape']),
    ('fit', 'A sudden fit of coughing woke me up.', ['sudden and vigorous appearance of a symptom']),
    ('bank', 'I was thinking about the bank.', []),
    ('period', 'Tell me about the period.', []),
    ('light', 'What do you mean by light?', []),
    ('charge', 'Can you explain the charge?', []),
]


def main(args):
    args.output.mkdir(parents=True, exist_ok=False)
    protocol = {'version': 1, 'source': 'authored English falsification examples; not independent or bilingual review',
                'margin': 0.02, 'query': 'query: {sentence} Word: {word}.', 'passage': 'passage: {word}: {label}',
                'cases': [{'word': w, 'sentence': s, 'acceptable': a} for w, s, a in CASES],
                'candidate_source_sha256': hashlib.sha256(args.pack.read_bytes()).hexdigest()}
    protocol_raw = (json.dumps(protocol, ensure_ascii=False, indent=2) + '\n').encode()
    (args.output / 'protocol.json').write_bytes(protocol_raw)
    db = sqlite3.connect(args.pack.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
    labels = {w: [r[0] for r in db.execute('SELECT DISTINCT s.label FROM vocabulary v JOIN senses s ON s.id=v.sense_id WHERE v.source=? ORDER BY s.label', (w,))] for w, _, _ in CASES}
    for w, _, acceptable in CASES:
        if not set(acceptable).issubset(labels[w]):
            raise ValueError('Expected label absent from fixed pack: ' + w)
    tokenizer = Tokenizer.from_file(str(args.model / 'onnx/tokenizer.json'))
    tokenizer.enable_truncation(max_length=512)
    tokenizer.enable_padding(pad_id=1, pad_token='<pad>')
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 2
    opts.inter_op_num_threads = 1
    start = time.perf_counter()
    session = ort.InferenceSession(str(args.model / 'onnx/model_qint8_avx512_vnni.onnx'), sess_options=opts, providers=['CPUExecutionProvider'])
    load_ms = (time.perf_counter() - start) * 1000
    names = {item.name for item in session.get_inputs()}

    def encode(texts):
        encodings = tokenizer.encode_batch(texts)
        inputs = {'input_ids': np.array([e.ids for e in encodings], dtype=np.int64),
                  'attention_mask': np.array([e.attention_mask for e in encodings], dtype=np.int64),
                  'token_type_ids': np.array([e.type_ids for e in encodings], dtype=np.int64)}
        result = session.run(None, {k: v for k, v in inputs.items() if k in names})[0]
        mask = inputs['attention_mask'][..., None]
        pooled = (result * mask).sum(axis=1) / mask.sum(axis=1)
        return pooled / np.linalg.norm(pooled, axis=1, keepdims=True)

    vectors = {word: encode([f'passage: {word}: {label}' for label in values]) for word, values in labels.items()}
    observations = []
    for word, sentence, acceptable in CASES:
        start = time.perf_counter()
        scores = vectors[word] @ encode([f'query: {sentence} Word: {word}.'])[0]
        elapsed = (time.perf_counter() - start) * 1000
        ranking = sorted(zip(labels[word], map(float, scores)), key=lambda x: (-x[1], x[0]))
        margin = ranking[0][1] - ranking[1][1]
        selected = ranking[0][0] if margin >= protocol['margin'] else None
        observations.append({'word': word, 'sentence': sentence, 'acceptable': acceptable,
                             'ranking': ranking, 'margin': margin, 'selected': selected,
                             'top_correct': ranking[0][0] in acceptable if acceptable else None,
                             'unsafe_selection': selected is not None and selected not in acceptable,
                             'query_ms': elapsed})
    report = {'protocol_sha256': hashlib.sha256(protocol_raw).hexdigest(), 'observations': observations,
              'cases': len(CASES), 'selected': sum(x['selected'] is not None for x in observations),
              'unsafe_selections': sum(x['unsafe_selection'] for x in observations),
              'unambiguous_cases': sum(bool(x['acceptable']) for x in observations),
              'top_correct': sum(x['top_correct'] is True for x in observations),
              'load_ms': load_ms, 'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
              'query_median_ms': float(np.median([x['query_ms'] for x in observations])),
              'query_p95_ms': float(np.percentile([x['query_ms'] for x in observations], 95)),
              'device': 'OZZZ-OS x86_64 CPU, two inference threads; not mobile latency',
              'providers': session.get_providers(), 'mobile_qualified': False}
    (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'observations'}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--pack', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    main(parser.parse_args())
