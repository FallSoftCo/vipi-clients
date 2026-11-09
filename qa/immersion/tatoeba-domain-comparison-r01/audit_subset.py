#!/usr/bin/env python3
"""Independent aggregate audit of the retained subset, without target review."""
import collections
import gzip
import hashlib
import json
import os
import resource
import signal
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from build_corpus_exclusions import fingerprint

WORK = Path('/home/ai/Development/investigations/vipi-tatoeba-domain-comparison-20261108-r01')


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    started = time.monotonic()
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    os.nice(10)
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024**2,) * 2)
    def timeout(*_):
        raise TimeoutError('Subset audit exceeded 60 seconds')
    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(60)
    destination = WORK / 'subset-root-audit-r01.json'
    assert not destination.exists()
    receipt = dict(complete=False, production=False, auditor_sha256=sha(Path(__file__)))
    try:
        freeze = json.loads((WORK / 'input-freeze.json').read_text())
        assert sha(WORK / 'exclusions.json') == freeze['exclusions']['sha256']
        excluded = set(json.loads((WORK / 'exclusions.json').read_text())['hashes'])
        fetched = WORK / 'remote-evidence/outputs/fetch'
        original_receipt = json.loads((fetched / 'receipt.json').read_text())
        assert original_receipt['complete'] and original_receipt['accepted_pairs'] == 40000
        for name, identity in original_receipt['outputs'].items():
            path = fetched / name
            assert path.stat().st_size == identity['bytes'] and sha(path) == identity['sha256']
        all_ids, pair_ids = set(), set()
        fulltext = {language: set() for language in ['en', 'es']}
        owners = {language: collections.Counter() for language in fulltext}
        lengths = {language: collections.Counter() for language in fulltext}
        components = collections.Counter()
        previous_rank = ''
        with gzip.open(fetched / 'en-es-pairs.jsonl.gz', 'rt') as records, (fetched / 'en-es.txt').open() as aligned_text:
            for index, line in enumerate(records):
                row = json.loads(line)
                assert row['index'] == index and row['pair'] == 'en-es'
                assert row['pair_id'] not in pair_ids
                pair_ids.add(row['pair_id'])
                source, target = row['source'], row['target']
                assert source['language'] == 'en' and target['language'] == 'es'
                assert source['component'] == target['component']
                components[source['component']] += 1
                canonical = sorted([source['id'], target['id']])
                assert row['provenance']['direct_edge'] == canonical
                rank = hashlib.sha256(('vipi-tatoeba-domain-r01|' + '|'.join(map(str, canonical))).encode()).hexdigest()
                assert row['provenance']['hash_selection_rank'] == rank and rank > previous_rank
                previous_rank = rank
                assert row['provenance']['source_database_sha256'] == 'a07e1d33c67a876df78c2221ce568e67c5aea773fae8c5d814458838095b28a5'
                for endpoint in [source, target]:
                    assert endpoint['partition'] == 'development'
                    text, lang, tokens = endpoint['text'], endpoint['language'], endpoint['tokens']
                    digest = fingerprint(lang, text).hex()
                    assert digest == endpoint['fingerprint'] and digest not in excluded
                    assert 2 <= len(tokens) <= 60 and '|||' not in text
                    previous_end = 0
                    for token in tokens:
                        start, end = token['codepoints']
                        assert previous_end <= start < end and text[start:end] == token['text']
                        assert token['utf16'] == [len(text[:p].encode('utf-16-le')) // 2 for p in [start, end]]
                        previous_end = end
                    fulltext[lang].add(digest)
                    owners[lang][endpoint['owner']] += 1
                    lengths[lang][len(tokens)] += 1
                    all_ids.add(endpoint['id'])
                expected = ' ||| '.join(' '.join(t['text'].casefold() for t in e['tokens']) for e in [source, target]) + '\n'
                assert next(aligned_text) == expected
            assert index + 1 == 40000 and aligned_text.read() == ''
        control = next(r for r in freeze['pgv_control'] if r['name'] == 'en-es-pairs.jsonl.gz')
        assert sha(Path(control['path'])) == control['sha256']
        overlaps = collections.Counter()
        with gzip.open(control['path'], 'rt') as records:
            for line in records:
                row = json.loads(line)
                matches = [e['fingerprint'] in fulltext[e['language']] for e in [row['source'], row['target']]]
                overlaps['pairs_with_any_shared_fulltext'] += any(matches)
                overlaps['pairs_with_both_shared_fulltexts'] += all(matches)
                overlaps['en_endpoint_occurrences'] += matches[0]
                overlaps['es_endpoint_occurrences'] += matches[1]
        receipt.update(complete=True, subset_receipt_sha256=sha(fetched / 'receipt.json'),
                       pair_count=len(pair_ids), distinct_sentence_ids=len(all_ids),
                       distinct_components=len(components), largest_component_pairs=max(components.values()),
                       top_component_counts=components.most_common(10), pgv_fulltext_overlap=dict(overlaps),
                       endpoint_aggregates={lang: dict(distinct_fulltexts=len(fulltext[lang]),
                           total_tokens=sum(length * count for length, count in lengths[lang].items()),
                           mean_tokens=sum(length * count for length, count in lengths[lang].items()) / 40000,
                           distinct_owners=len(owners[lang]), largest_owner_pair_count=max(owners[lang].values()),
                           blank_owner_pair_count=owners[lang].get('', 0)) for lang in fulltext},
                       limits='Development-only direct pairs with exact provenance and geometry; contributor/component concentration is retained. No semantic quality or conversational coverage established.')
    except BaseException as error:
        receipt['error'] = repr(error)
        raise
    finally:
        receipt['seconds'] = time.monotonic() - started
        receipt['VmHWM_bytes'] = int(next(l.split()[1] for l in Path('/proc/self/status').read_text().splitlines() if l.startswith('VmHWM:'))) * 1024
        with destination.open('x') as stream:
            json.dump(receipt, stream, indent=2)
            stream.write('\n')
        print(json.dumps(receipt))


if __name__ == '__main__':
    main()
