#!/usr/bin/env python3
"""Freeze source-frequency keys and evaluated-message exclusions before mining."""
import bisect
import collections
import hashlib
import json
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
QA = ROOT / 'qa/immersion'
EVIDENCE = Path('/home/ai/Development/investigations/vipi-immersion-reconciliation-20261107-r01')
sys.path.insert(0, str(QA))
from build_corpus_exclusions import fingerprint


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def norm(text):
    return ' '.join(unicodedata.normalize('NFC', text).casefold().split())


def main():
    out = EVIDENCE / 'corpus-phrase-extraction-r01'
    out.mkdir(exist_ok=True)
    assert not (out / 'input-freeze.json').exists()
    protocol_path = HERE / 'protocol.json'
    protocol = json.loads(protocol_path.read_text())
    paths = sorted(set((QA / 'coverage_ceiling_experiment').glob('*protocol*.json')) |
                   set(EVIDENCE.glob('*protocol*.json')) |
                   {QA / 'nlp-template-comparison-r01/authored-cases.json'})
    exclusions, records = set(), []
    languages = {'en', 'es', 'fr', 'de', 'it', 'pt', 'sw', 'ja', 'zh', 'ko', 'ar'}
    for path in paths:
        data = json.loads(path.read_text())
        if not isinstance(data, dict):
            continue
        cases = data.get('cases', data.get('messages', []))
        if not isinstance(cases, list):
            continue
        count = 0
        for row in cases:
            if not isinstance(row, dict):
                continue
            text = row.get('text', row.get('original'))
            language = row.get('source_language', row.get('source', row.get('input_language', 'en')))
            if language not in languages or not isinstance(text, str):
                continue
            exclusions.add(fingerprint(language, text).hex())
            count += 1
        if count:
            records.append(dict(path=str(path), sha256=sha(path), full_source_message_records=count))
    (out / 'evaluation-exclusion-hashes.json').write_text(json.dumps(dict(
        algorithm='Existing build_corpus_exclusions.fingerprint; exact full evaluated source messages only.',
        scope='No isolated-word/subphrase translation requests or model outputs are imported as evaluated conversation sentences.',
        inputs=records, hashes=sorted(exclusions)), indent=2) + '\n')

    geometry = Path('/home/ai/Development/investigations/vipi-android-readiness-20261107-r01/top-down-source-lookup-r01/tokenizer-r87b/rows.jsonl')
    assert sha(geometry) == protocol['source_frequency_selection']['native_geometry_sha256']
    counts = collections.Counter()
    messages = collections.Counter()
    costs = collections.defaultdict(set)
    examples = collections.defaultdict(list)
    total = 0
    for line in geometry.open():
        row = json.loads(line)
        total += 1
        raw = row['text'].encode('utf-16-le')
        words = row['native_source_word_ranges_utf16']
        starts, ends = [w[0] for w in words], [w[1] for w in words]
        seen = set()
        for start, end in row['native_window_ranges_utf16']:
            key = norm(raw[2 * start:2 * end].decode('utf-16-le'))
            cost = bisect.bisect_right(ends, end) - bisect.bisect_left(starts, start)
            assert 1 <= cost <= 8
            counts[key] += 1
            costs[key].add(cost)
            seen.add(key)
        messages.update(seen)
        for key in seen:
            if len(examples[key]) < 3:
                examples[key].append(row['id'])
    inventory = []
    for key in counts:
        if messages[key] >= 2:
            inventory.append(dict(source_language='en', source_key=key,
                                  source_message_frequency=messages[key], occurrence_frequency=counts[key],
                                  observed_native_costs=sorted(costs[key]), source_example_ids=examples[key]))
    inventory.sort(key=lambda r: (-r['source_message_frequency'], -r['occurrence_frequency'], r['source_key']))
    single = [r for r in inventory if r['observed_native_costs'] == [1]][:3000]
    multi = [r for r in inventory if min(r['observed_native_costs']) >= 2][:5000]
    selected = dict(production=False, source_only_selection=True, source_messages=total,
                    ranking='Distinct source-message frequency, occurrence frequency, normalized lexical key; no target data or score.',
                    normalization='NFC casefold and whitespace collapse; original source remains in exact native protocol.',
                    inputs=dict(geometry_sha256=sha(geometry), protocol_sha256=sha(protocol_path)),
                    eligible_repeated_source_keys=len(inventory), unigram_keys=single, multiword_keys=multi,
                    mixed_native_cost_keys_withheld=sum(1 for r in inventory if 1 in r['observed_native_costs'] and len(r['observed_native_costs']) > 1))
    (out / 'source-frequency-keys.json').write_text(json.dumps(selected, ensure_ascii=False, indent=2) + '\n')
    freeze = dict(production=False, frozen_before_parallel_pair_text_and_alignment=True,
                  protocol_sha256=sha(protocol_path), builder_sha256=sha(Path(__file__)),
                  exclusions_sha256=sha(out / 'evaluation-exclusion-hashes.json'),
                  source_frequency_sha256=sha(out / 'source-frequency-keys.json'),
                  evaluated_message_hashes=len(exclusions), exclusion_protocols=len(records),
                  unigram_keys=len(single), multiword_keys=len(multi), source_messages=total,
                  source_key_eligibility='Research candidate reach only, not safe contextual meanings or publication.')
    (out / 'input-freeze.json').write_text(json.dumps(freeze, indent=2) + '\n')
    print(json.dumps(freeze))


if __name__ == '__main__':
    main()
