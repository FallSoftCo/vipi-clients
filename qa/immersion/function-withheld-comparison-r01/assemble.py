#!/usr/bin/env python3
"""Assemble retained selection snapshots; never call a selector or model."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import time

HERE = Path(__file__).resolve().parent
BASE = Path('/home/ai/Development/investigations')
WORK = BASE / 'vipi-function-withheld-comparison-20261108-r01'
OLD = BASE / 'vipi-source-role-veto-20261108-r01/projection-r01'
PROTOCOL_SHA = 'a5d59d124b8aa7e43325c5730ef444effac1fa467e3830133ba6ba33eb25dcdb'


def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''):
            h.update(b)
    return h.hexdigest()


def write(p, value):
    with p.open('x') as f:
        f.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def vm():
    return {k: int(v.split()[0]) * 1024 for k, v in
            (s.split(':', 1) for s in Path('/proc/self/status').read_text().splitlines()
             if s.startswith(('VmHWM:', 'VmPeak:', 'VmRSS:')))}


def mixed(text, candidates):
    raw = text.encode('utf-16-le')
    end = len(raw) // 2
    for c in sorted(candidates, key=lambda c: c['focus_utf16'][0], reverse=True):
        a, b = c['focus_utf16']
        assert 0 <= a < b <= end
        assert text.encode('utf-16-le')[2*a:2*b].decode('utf-16-le') == c['source']
        raw = raw[:2*a] + c['target'].encode('utf-16-le') + raw[2*b:]
        end = a
    return raw.decode('utf-16-le')


def key(c):
    return tuple(c['focus_utf16']), c['target'], c['reading']


def retained(path, wanted):
    result = {}
    with gzip.open(path, 'rt') as f:
        for line in f:
            row = json.loads(line)
            if row['id'] in wanted:
                assert row['id'] not in result
                result[row['id']] = row
    assert set(result) == wanted
    return result


def main():
    start = time.monotonic()
    assert sha(WORK / 'protocol.json') == PROTOCOL_SHA
    protocol = json.loads((WORK / 'protocol.json').read_text())
    bounds = protocol['resource_bounds']
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    resource.setrlimit(resource.RLIMIT_AS, (bounds['max_process_address_space_bytes'],)*2)
    def timeout(*args):
        raise TimeoutError('60-second assembly limit')
    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(bounds['max_seconds'])
    free = shutil.disk_usage(WORK).free
    assert free >= bounds['minimum_free_bytes'] + bounds['max_added_output_bytes']
    out = WORK / 'assembly-r01'
    out.mkdir(exist_ok=False)
    try:
        bindings = {'review-packet.json': protocol['existing_packet_sha256'],
                    'decisions.jsonl.gz': protocol['decisions_sha256'],
                    'complete-baseline-cache.jsonl.gz': protocol['baseline_cache_sha256']}
        for name, expected in bindings.items():
            assert sha(OLD / name) == expected, name
        write(out / 'execution-freeze.json', {'protocol_sha256': PROTOCOL_SHA, 'code_sha256': sha(Path(__file__)), 'inputs': bindings, 'free_bytes_before': free, 'bounds': bounds, 'before_outputs': True})
        old = json.loads((OLD / 'review-packet.json').read_text())
        chosen = protocol['source_selection']
        ids = {c['source_id'] for c in chosen}
        assert len(chosen) == len(ids) == 16
        oldcases = {c['source_id']: c for c in old['cases'] if c['known'] == 'none'}
        assert set(oldcases) == ids
        cache = retained(OLD / 'complete-baseline-cache.jsonl.gz', ids)
        decisions = retained(OLD / 'decisions.jsonl.gz', ids)
        cases = []
        totals = {'cases': 16, 'before_outputs_verified': 0, 'prior_union_units': 0, 'added_union_units': 0, 'union_units': 0, 'after_only_units': 0}
        for selection in chosen:
            ident, pair = selection['source_id'], selection['pair']
            prior, row = oldcases[ident], cache[ident]
            assert (prior['review_id'], prior['pair'], prior['source']) == (selection['review_id'], pair, row['text'])
            for k in ['native_words_utf16', 'source_masks', 'protected_ranges_utf16']:
                assert prior[k] == row[k]
            candidates = dict(row['pairs'][pair]['candidates'])
            oldcandidates = {c['original_trace_index']: c for c in prior['candidates']}
            assert set(candidates) == set(oldcandidates)
            for i, c in candidates.items():
                assert c == oldcandidates[i]['candidate']
            previous = {key(u): i for i, u in enumerate(prior['review_union'])}
            union, arms = {}, {}
            for arm in protocol['arms']:
                snapshots = {}
                for phase, state in [('before', protocol['before_known']), ('after', protocol['after_known'])]:
                    indices = decisions[ident]['pairs'][pair]['decisions'][state][arm]['selected_indices']
                    assert len(indices) == len(set(indices))
                    selected = [candidates[i] for i in indices]
                    text = mixed(row['text'], selected)
                    candidate_ids = [c['id'] for c in selected]
                    if phase == 'before':
                        assert indices == prior['arms'][arm]['selected_indices']
                        assert candidate_ids == prior['arms'][arm]['selected_candidate_ids']
                        assert text == prior['arms'][arm]['mixed_output']
                        totals['before_outputs_verified'] += 1
                    snapshots[phase] = {'existing_known_state': state, 'selected_indices': indices, 'selected_candidate_ids': candidate_ids, 'mixed_output': text, 'selected_cost': sum(c['cost'] for c in selected), 'catalog_content_anchor_words': sum(c['content_anchor_native_words'] for c in selected), 'empty': not indices}
                    for i in indices:
                        c = candidates[i]
                        identity = key(c)
                        if identity not in union:
                            union[identity] = {'focus_utf16': c['focus_utf16'], 'target': c['target'], 'reading': c['reading'], 'prior_union_index': previous.get(identity), 'previously_reviewed_in_case': identity in previous, 'candidate_indices': [], 'candidate_ids': [], 'before_arms': [], 'after_arms': []}
                        u = union[identity]
                        if i not in u['candidate_indices']:
                            u['candidate_indices'].append(i)
                            u['candidate_ids'].append(c['id'])
                        u[phase + '_arms'].append(arm)
                before, after = snapshots['before']['selected_indices'], snapshots['after']['selected_indices']
                snapshots['removed_indices'] = sorted(set(before) - set(after))
                snapshots['added_indices'] = sorted(set(after) - set(before))
                arms[arm] = snapshots
            assert set(previous) <= set(union)
            totals['prior_union_units'] += len(previous)
            totals['added_union_units'] += sum(not u['previously_reviewed_in_case'] for u in union.values())
            totals['union_units'] += len(union)
            totals['after_only_units'] += sum(not u['before_arms'] and bool(u['after_arms']) for u in union.values())
            used = {i for u in union.values() for i in u['candidate_indices']}
            cases.append({**selection, 'source': row['text'], 'review_only_preceding_context': prior['review_only_preceding_context'], **{k: row[k] for k in ['native_words_utf16', 'source_masks', 'protected_ranges_utf16']}, 'arms': arms, 'review_union': list(union.values()), 'selected_candidate_evidence': [oldcandidates[i] for i in sorted(used)]})
        assert totals['before_outputs_verified'] == 96
        packet = {'schema': 'vipi.function-withheld-review-packet.r01', 'production': False, 'semantic_labels_present': False, 'protocol_sha256': PROTOCOL_SHA, 'policy': 'Existing all_function selection state is a catalog-function withholding policy, not a user-knowledge claim.', 'old_packet_sha256': protocol['existing_packet_sha256'], 'cases': cases}
        write(out / 'review-packet.json', packet)
        added_bytes = sum(p.stat().st_size for p in out.iterdir() if p.is_file())
        assert added_bytes < bounds['max_added_output_bytes'] - 65536
        assert shutil.disk_usage(WORK).free >= bounds['minimum_free_bytes']
        receipt = {'complete': True, 'production': False, 'semantic_labels_present': False, 'protocol': {'path': str(WORK / 'protocol.json'), 'sha256': PROTOCOL_SHA}, 'code_sha256': sha(Path(__file__)), 'inputs': bindings, 'totals': totals, 'seconds': time.monotonic() - start, 'measurement': vm(), 'free_bytes_before': free, 'free_bytes_after': shutil.disk_usage(WORK).free, 'bounds': bounds, 'outputs': {p.name: {'path': str(p), 'sha256': sha(p), 'bytes': p.stat().st_size} for p in out.iterdir() if p.is_file()}}
        write(out / 'receipt.json', receipt)
        write(HERE / 'assembly-receipt.json', receipt)
        print(json.dumps(receipt))
    except BaseException as exc:
        write(out / 'failure.json', {'error': repr(exc), 'seconds': time.monotonic() - start, 'measurement': vm()})
        raise


if __name__ == '__main__':
    main()
