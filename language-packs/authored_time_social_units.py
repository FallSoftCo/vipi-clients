#!/usr/bin/env python3
"""Explicit time words and everyday social nouns from existing authored forms.

Training-only frequency can prioritize these topics. Neither evaluation corpus
is read here. Whole-reference permission is withheld for every new unit carrier.
Known shared written source meanings remain excluded from this broader scope.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path

import authored_conversation as base
import authored_conversation_expansion as expansion
import authored_conversation_routines as routines
import authored_swahili_contexts as sw_contexts
from authored_everyday_units import form_variants, replace_focus, PINNED
from build_wiktextract import canonical, digest_file
from mapping_catalog import validate

TOPICS = ('time_duration', 'today', 'tomorrow', 'yesterday', 'week', 'month',
    'year', 'price', 'car', 'message', 'help_noun', 'work_job', 'bag_container',
    'weather_conditions', 'morning_time', 'night_time', 'exam_school',
    'news_information', 'question', 'problem', 'plan_arrangement')
EQUIVALENT_FRAMES = {'needs_time':'time_duration', 'needs_help':'help_noun',
    'requests_job_search':'work_job', 'requests_send_message':'message'}
EXPORT_SHA = '70a724dc860dd187ec28f341e8fff527ac8cf8b5c368412b52d4f78076b8ed51'
UNIT_HELPER_SHA = '62776d158825613a89e7523c5504dd37bd8702ee1c5c07033bb8f3953b8576d5'


def permitted_source(topic, language):
    # Single written forms cannot pick between these senses. The pre-existing
    # exact sentence contexts stay available; no target-conditioned guess here.
    return not ((language == 'es' and topic in ('tomorrow', 'morning_time')) or
                (language == 'zh' and topic in ('question', 'problem')))


def records(export):
    for name, expected in PINNED.items():
        if digest_file(Path(__file__).with_name(name)) != expected:
            raise ValueError('Changed authored source: '+name)
    if digest_file(Path(__file__).with_name('authored_everyday_units.py')) != UNIT_HELPER_SHA:
        raise ValueError('Changed explicitly bounded case helper')
    if digest_file(export) != EXPORT_SHA:
        raise ValueError('Changed prior frame export')
    data = dict(base.DATA, **expansion.DATA, **routines.DATA)
    seeds = []
    for row in base.records(data):
        topic = row['logical_id'].split(':')[1].removeprefix('conversation_')
        if topic in TOPICS and permitted_source(topic, row['source_language']):
            seeds.append((topic, row))
    for row in sw_contexts.records():
        topic = row['logical_id'].split(':')[1].removeprefix('swahili_context_')
        if topic in TOPICS and permitted_source(topic, row['source_language']):
            seeds.append((topic, row))
    if len(seeds) != 2270:
        raise ValueError('Unexpected explicitly permitted topic/direction count: '+str(len(seeds)))
    for line in export.read_text().splitlines():
        original = json.loads(line)['record']
        topic = EQUIVALENT_FRAMES.get(original['logical_id'].split(':')[1])
        if topic:
            row = deepcopy(original); row['meaning'] = data[topic][0]
            validate(row)
            if row != original:
                yield row
    for topic, original in seeds:
        for left_index, left in enumerate(form_variants(original['source'], original['source_language'])):
            for right_index, right in enumerate(form_variants(original['target'], original['target_language'])):
                row = deepcopy(original)
                replace_focus(row, 'source', left); replace_focus(row, 'target', right)
                row['logical_id'] = ('vipi-time-social-unit-r1:'+topic+':'
                    +row['source_language']+'-'+row['target_language']+':'+str(left_index)+str(right_index))
                row['usage'].pop('context_pattern', None)
                row['usage'].update(context_extent='local_phrase', lexical_unit=True,
                    whole_reference=False,
                    context_generalization='explicitly assessed complete time expression or noun; no example verb required',
                    source_frame_span=row['source_span'][:], target_frame_span=row['target_span'][:],
                    source_frame_pattern=[{'focus':left}], target_frame_pattern=[{'focus':right}],
                    permitted_context='The exact assessed sense and complete unique native form must occur on both sides. External person, tense, negation, ownership and number remain unchanged.',
                    abstain_when=['Either complete native counterpart is missing.',
                        'Repeated source/target forms, conflicting senses or readings prevent unique alignment.',
                        'Protected text, incomplete native boundaries or unsupported morphology exclude the candidate.'])
                row['provenance']['priority_basis'] = 'Existing everyday topics plus AfriSenti training-only frequency priorities; no evaluation utterance read'
                row['provenance']['case_scope'] = 'First-letter lower/upper only for these en/es/fr/it/pt/sw forms; German capitalization unchanged'
                row['provenance']['whole_reference_eligibility'] = 'False: case carrier contexts do not approve whole-message translation'
                validate(row)
                yield row


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--existing-export', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); rows = list(records(args.existing_export))
    assert len({r['logical_id'] for r in rows}) == len(rows)
    args.output.mkdir(parents=True, exist_ok=False)
    path = args.output/'records.jsonl'
    path.write_text(''.join(canonical(row)+'\n' for row in rows))
    print(canonical({'records':len(rows), 'units':sum(r['logical_id'].startswith('vipi-time-social-unit-r1:') for r in rows),
        'records_sha256':digest_file(path), 'authoring_source_sha256':digest_file(Path(__file__)), 'release_ready':False}))
