#!/usr/bin/env python3
"""Withhold the unresolved abstract thing family; preserve native r02 evidence."""
import argparse
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    q = Path(__file__).resolve().parent
    prior = q / 'reviewed-source-unit-native-candidate-r02.json'
    assert sha(prior) == '67f041f3024c0e3679d54de9afa2debcebba1ad42e0a79b7bb0e4aacb90f2f60'
    audit = q / 'swahili-thing-scope-audit-r03.json'
    data = json.loads(prior.read_text())
    pair = data['pairs']['en-sw']
    removed = [e for e in pair['entries'] if e['id'] in {'word-en-sw-thing', 'word-en-sw-things'}]
    assert {e['source'] for e in removed} == {'thing', 'things'}
    pair['entries'] = [e for e in pair['entries'] if e not in removed]
    pair['withheld_target_scope'] = [dict(entry=e, audit_file=audit.name,
        audit_sha256=sha(audit), reason='Unqualified abstract/concrete sense split. The plural shares the same unresolved lexeme sense, so it is withheld without claiming a newly observed plural error.') for e in removed]
    pair['summary']['eligible_units'] -= 2
    pair['summary']['content_units'] -= 2
    pair['summary']['withheld_target_scope_units'] = 2
    data['revision'] = 3
    data['pack_version'] = 'reviewed-source-starter-en-v003'
    data['status'] = 'Research candidate with a conservative sense withholding; not enabled in production. Native r02 results remain the measured evidence, not a measurement of revision3.'
    data['prior_candidate_sha256'] = sha(prior)
    data['revision_compiler_sha256'] = sha(Path(__file__))
    data['changes_from_revision2'] = dict(withheld=['word-en-sw-thing','word-en-sw-things'],
        reason='Object versus abstract matter/custom is not resolved by the generic English source form.',
        matching_algorithm_unchanged=True,frozen_scores_and_captures_changed=False,
        native_revision3_capture_completed=False,
        existing_translation_fallback_modified=False)
    data['input_sha256'][str(audit)] = sha(audit)
    data['limitations'].append('Removing a source-only face does not guarantee the unchanged full-translation fallback will avoid the same sense. No revision3 runtime or coverage claim is made.')
    assert [data['pairs'][p]['summary']['eligible_units'] for p in ['en-sw','en-ja','en-es']] == [107,46,43]
    assert not args.output.exists()
    args.output.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    print(sha(args.output))


if __name__ == '__main__':
    main()
