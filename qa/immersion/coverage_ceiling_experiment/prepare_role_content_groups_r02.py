#!/usr/bin/env python3
"""Additive correction: curated concepts override incomplete raw lemma groups."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path

Q = Path(__file__).resolve().parent
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
old = json.loads((Q/'role-content-candidate-r01.json').read_text())
baseline = json.loads((Q/'content-expansion-candidate-r01.json').read_text())
audit = json.loads((Q/'content-expansion-concept-group-audit-r02.json').read_text())
frequency = json.loads((Q/'scaled-training-source3000-r01.json').read_text())
canonical = {name: group[0] for group in audit['alias_groups'] for name in group}
# The retained source inventory independently gives both noun forms the same
# canonical family. This additional omission is explicit, not silently folded
# into the previous four-merge audit or its scores.
canonical.update({'name': 'name', 'names': 'name'})
curated = {}
groups = defaultdict(set)
for pair in baseline['pairs'].values():
    for entry in pair['entries']:
        if entry['category'] != 'content':
            continue
        concept = canonical.get(entry['concept_id'], entry['concept_id'])
        assert entry['source'] not in curated or curated[entry['source']] == concept
        curated[entry['source']] = concept
        groups[concept].add(entry['source'])
raw_to_curated = {}
for source, concept in curated.items():
    raw_family = old['source_families'].get(source)
    if raw_family and not raw_family.startswith('unresolved:'):
        assert raw_family not in raw_to_curated or raw_to_curated[raw_family] == concept
        raw_to_curated[raw_family] = concept
families = dict(old['source_families'])
for source, raw_family in families.items():
    if raw_family and not raw_family.startswith('unresolved:'):
        families[source] = raw_to_curated.get(raw_family, raw_family)
families.update(curated)
for entry in old['entries']:
    # A new target reuses an existing source concept, e.g. parents, rather
    # than replacing the already reviewed grouping with raw lemma 'parent'.
    families[entry['source']] = curated.get(entry['source'], families.get(entry['source']) or entry['concept'])
order = []
for row in frequency['rows']:
    source = row['source']
    family = families.get(source)
    if source not in curated and (not family or family.startswith('unresolved:') or old['source_families'].get(source) not in old['learned_family_order']):
        continue
    if family not in order:
        order.append(family)
splits = []
for concept, sources in sorted(groups.items()):
    prior = {old['source_families'].get(s) or concept for s in sources}
    if len(prior) > 1:
        splits.append({'curated_concept': concept, 'sources': sorted(sources), 'incorrect_r01_families': sorted(prior)})
candidate = dict(old, source_families=families, learned_family_order=order,
                 grouping_revision=2, prior_candidate_sha256=sha(Q/'role-content-candidate-r01.json'))
out = Q/'role-content-candidate-r02.json'
assert not out.exists()
out.write_text(json.dumps(candidate, ensure_ascii=False, indent=2) + '\n')
receipt = {'production': False, 'fresh_validation': False,
           'prior_r01_outputs_preserved': True, 'targets_and_role_policy_unchanged': old['entries'] == candidate['entries'],
           'scope': 'The r01 adapter incorrectly split authoritative curated synonym/number groups through incomplete/unresolved raw lemma labels. Reuse curated groups plus the already documented four merges. Keep all original r01 scores as superseded diagnostic output.',
           'known_order_correction': 'Global TRAIN frequency order after authoritative concept grouping. Add previously omitted curated families such as mother/mom; incomplete raw native source analyses cannot hide these known vocabulary groups. Other raw resolved families remain the previously declared simulation, not validated learner concepts.',
           'curated_groups': len(groups), 'split_groups_corrected': splits,
           'additional_attested_number_merge': {'forms': ['name', 'names'], 'concept': 'name',
               'basis': 'Both existing content entries are nouns and their retained source native family is name; the prior four-merge audit omitted this pair.'},
           'old_global_family_count': len(old['learned_family_order']), 'corrected_global_family_count': len(order),
           'candidate_sha256': sha(out),
           'inputs': {name: sha(Q/name) for name in ['role-content-candidate-r01.json', 'content-expansion-candidate-r01.json', 'content-expansion-concept-group-audit-r02.json', 'scaled-training-source3000-r01.json', Path(__file__).name]}}
out = Q/'role-content-grouping-correction-r02.json'
assert not out.exists()
out.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
print('corrected', len(splits), 'groups', 'candidate', receipt['candidate_sha256'])
