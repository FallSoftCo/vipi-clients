#!/usr/bin/env python3
"""Recompute the frozen TRAIN-only short-unit selection; never reads holdout data."""
import argparse
import collections
import hashlib
import json
import re
from pathlib import Path


def normalize(text):
    return re.sub(r'\s+', ' ', text.replace('’', "'").strip()).casefold().strip(' .!?"“”')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--train', required=True, type=Path)
    parser.add_argument('--receipt', required=True, type=Path)
    args = parser.parse_args()
    q = Path(__file__).resolve().parent
    frozen_path = q / 'short-conversation-source-freeze-r01.json'
    frozen = json.loads(frozen_path.read_text())
    raw = args.train.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    assert digest == frozen['source_sha256'], 'Wrong TRAIN source; no alternate split admitted'
    units = collections.defaultdict(lambda: dict(turns=set(), whole=0, clause=0))
    total = short = all_short = 0
    for ci, conversation in enumerate(json.loads(raw)):
        if conversation['context_dataset'] != 'convai2':
            continue
        for ti, (speaker, text) in enumerate(conversation['dialog']):
            if speaker != 0:
                continue
            total += 1
            all_short += 1 <= len(normalize(text).split()) <= 5
            parts = re.split(r'(?<=[.!?])\s+', text.strip())
            candidates = [('whole', text)] + ([('clause', x) for x in parts] if len(parts) > 1 else [])
            for kind, unit in candidates:
                norm = normalize(unit)
                if not 1 <= len(norm.split()) <= 5 or not any(c.isalpha() for c in norm):
                    continue
                units[norm]['turns'].add((ci, ti))
                units[norm][kind] += 1
                if kind == 'whole':
                    short += 1
    ranked = sorted(units, key=lambda k: (-len(units[k]['turns']), -units[k]['whole'], k))
    selected = [s for s in ranked if s not in frozen['exclusions']][:50]
    assert selected == [r['source'] for r in frozen['rows']]
    for row in frozen['rows']:
        u = units[row['source']]
        assert sorted(u['turns']) == row['training_turn_ids'] or [list(x) for x in sorted(u['turns'])] == row['training_turn_ids']
        assert len(u['turns']) == row['train_distinct_turns']
        assert u['whole'] == row['train_whole_turns']
        assert u['clause'] == row['train_clause_occurrences']
    union = set().union(*(units[s]['turns'] for s in selected))
    result = dict(production=False, training_only=True, train_sha256=digest,
        frozen_source_sha256=hashlib.sha256(frozen_path.read_bytes()).hexdigest(),
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        exact50_source_order_and_all_turn_counts_reproduced=True,
        training_free_human_turns=total, training_short_whole_turns_with_letters=short,
        training_short_whole_turns_including_nonlexical=all_short,
        distinct_short_units=len(units), selected_union_turns=len(union),
        selected_whole_turn_occurrences=sum(units[s]['whole'] for s in selected),
        limits=['Punctuation-delimited clause reach is not whole-turn reach.',
                'Crowdsourced persona TRAIN frequency is not worldwide private-chat frequency.',
                'No target or held-out text influences source ranking.'])
    assert not args.receipt.exists()
    args.receipt.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
