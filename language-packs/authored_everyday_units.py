#!/usr/bin/env python3
"""Explicit everyday noun scopes, with separately assessed case variants.

This authoring file never reads evaluation conversations. Existing complete
examples supply the native forms, and a pinned export supplies the old frame
revisions whose equivalent sense descriptions are explicitly reconciled.
Case-carrier examples are provenance, not new whole-message translations.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path

import authored_conversation as base
import authored_conversation_expansion as expansion
import authored_conversation_routines as routines
import authored_swahili_contexts as sw_contexts
from build_wiktextract import canonical, digest_file
from mapping_catalog import validate

CONTEXT_TOPICS = (
    'food', 'money', 'phone_device', 'friend_person', 'house_building',
    'school_place', 'office_place', 'meeting_event', 'bus_vehicle', 'train_vehicle',
    'airport_place', 'hotel_place', 'door_physical', 'breakfast_meal', 'lunch_meal',
    'dinner_meal', 'rain_weather', 'weekend_days', 'teacher_person', 'student_person',
    'email_message', 'movie_film', 'music_sound', 'photo_image', 'internet_network',
    'restaurant_place',
)
PHRASE_TOPICS = ('drinking_water', 'drinking_coffee', 'drinking_tea',
                 'eating_bread', 'eating_cheese', 'reading_book')
# These are explicit sense equivalences, not a string-similarity classifier.
EQUIVALENT_FRAMES = {
    'needs_food': 'food', 'needs_money': 'money', 'needs_water': 'drinking_water',
    'needs_breakfast': 'breakfast_meal', 'requests_hotel_search': 'hotel_place',
    'requests_restaurant_search': 'restaurant_place', 'requests_send_email': 'email_message',
    'phrase_frame_listening_music': 'music_sound', 'phrase_frame_liking_music': 'music_sound',
    'phrase_frame_watching_movie': 'movie_film',
    **{'phrase_frame_'+topic: topic for topic in PHRASE_TOPICS},
}
MEANINGS = {
    'food': 'food as nourishment for eating',
    'money': 'money as financial means, not the metal silver',
    'hotel_place': 'a hotel providing accommodation',
    'restaurant_place': 'a restaurant serving food',
    'email_message': 'an electronic mail message, not a postal letter',
    'breakfast_meal': 'breakfast as a morning meal',
    'music_sound': 'music as musical sound or musical art',
    'movie_film': 'a movie as an audiovisual work, not a material coating',
    'drinking_water': 'water as the liquid substance, not the act of watering',
    'drinking_coffee': 'coffee as a beverage, not a cafe establishment',
    'drinking_tea': 'tea as a beverage, not a meal called tea',
    'eating_bread': 'bread as food, not money or a verb',
    'eating_cheese': 'cheese as food, not a photographic instruction',
    'reading_book': 'a book as reading material, not a reservation verb or ledger operation',
}
EXPORT_SHA = '954f7a423234e1846bb9420c90e2491421eca1207f8718651927c809d657034a'
PINNED = {
    'authored_conversation.py': 'a007da1bdaea853cf8855df474ce915da7e3571a333579db8e7cd63fc763dfb3',
    'authored_conversation_expansion.py': '0db17fef8e99fba9172980853d041131e9a019ec315baee5c6f7148ca85c2114',
    'authored_conversation_routines.py': 'd9d8d8ca510223f79552474aede45c5b6e9a59ce12d15822d4a40bc5e654c721',
    'authored_swahili_contexts.py': 'e6027775ead688e8fcbd801c2bf273402e580734dabba8da2d66251a75b7e69f',
}


def topic_of(row):
    return row['logical_id'].split(':')[1]


def form_variants(word, language):
    # Only explicitly selected common nouns. Never lowercase German nouns,
    # remove accents, infer plurals, or split native morphology.
    if language not in ('en', 'es', 'fr', 'it', 'pt', 'sw'):
        return [word]
    return sorted({word[:1].lower()+word[1:], word[:1].upper()+word[1:]})


def replace_focus(row, side, word):
    a, b = row[side+'_span']; old = row[side+'_context']
    row[side] = word
    row[side+'_context'] = old[:a]+word+old[b:]
    row[side+'_span'] = [a, a+len(word)]


def records(export):
    for name, expected in PINNED.items():
        if digest_file(Path(__file__).with_name(name)) != expected:
            raise ValueError('Changed authored source: '+name)
    if digest_file(export) != EXPORT_SHA:
        raise ValueError('Changed existing frame export')
    data = dict(base.DATA, **expansion.DATA, **routines.DATA)
    means = {topic: MEANINGS.get(topic, data[topic][0]) for topic in CONTEXT_TOPICS}
    means.update({topic: MEANINGS[topic] for topic in PHRASE_TOPICS})
    seeds = []
    for row in base.records(data):
        topic = topic_of(row).removeprefix('conversation_')
        if topic in CONTEXT_TOPICS: seeds.append((topic, row))
    for row in sw_contexts.records():
        topic = topic_of(row).removeprefix('swahili_context_')
        if topic in CONTEXT_TOPICS: seeds.append((topic, row))
    existing = [json.loads(line)['record'] for line in export.read_text().splitlines()]
    for original in existing:
        topic = EQUIVALENT_FRAMES.get(topic_of(original))
        if topic:
            row = deepcopy(original); row['meaning'] = means[topic]
            # Pattern and reading permissions remain exactly as previously assessed.
            validate(row)
            if row != original: yield row
        concept = topic_of(original).removeprefix('phrase_frame_')
        if concept in PHRASE_TOPICS:
            seeds.append((concept, original))
    if len(seeds) != 32*110:
        raise ValueError('Every selected noun must cover all 110 directions')
    for topic, original in seeds:
        for left in form_variants(original['source'], original['source_language']):
            for right in form_variants(original['target'], original['target_language']):
                row = deepcopy(original)
                replace_focus(row, 'source', left); replace_focus(row, 'target', right)
                row['logical_id'] = ('vipi-everyday-unit-r1:'+topic+':'
                    +row['source_language']+'-'+row['target_language']+':'
                    +str(form_variants(original['source'], row['source_language']).index(left))
                    +str(form_variants(original['target'], row['target_language']).index(right)))
                row['meaning'] = means[topic]
                row['usage'].pop('context_pattern', None)
                row['usage'].update(context_extent='local_phrase', lexical_unit=True,
                    whole_reference=False,
                    context_generalization='explicitly assessed noun and written case variant; no fixed verb required',
                    source_frame_span=row['source_span'][:], target_frame_span=row['target_span'][:],
                    source_frame_pattern=[{'focus':left}], target_frame_pattern=[{'focus':right}],
                    permitted_context='The assessed noun sense must be represented by a complete unique native form on both sides. Surrounding grammar stays in the original language.',
                    abstain_when=['Either complete native form is missing.',
                        'Multiple occurrences or competing meanings/readings prevent unique alignment.',
                        'Protected text or native word boundaries exclude the candidate.'])
                row['provenance']['priority_basis'] = 'Explicit existing everyday topics; no reserved conversation supplied authoring'
                row['provenance']['case_scope'] = 'Only first-letter lower/upper variants of these common nouns in en/es/fr/it/pt/sw; German nouns unchanged'
                row['provenance']['whole_reference_eligibility'] = 'False: case-adjusted carrier contexts do not authorize whole-message translation'
                validate(row); yield row


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--existing-export', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args=p.parse_args(); rows=list(records(args.existing_export))
    assert len({r['logical_id'] for r in rows}) == len(rows)
    args.output.mkdir(parents=True, exist_ok=False)
    path=args.output/'records.jsonl';path.write_text(''.join(canonical(r)+'\n' for r in rows))
    print(canonical({'records':len(rows), 'units':sum(r['logical_id'].startswith('vipi-everyday-unit-r1:') for r in rows),
        'records_sha256':digest_file(path), 'authoring_source_sha256':digest_file(Path(__file__)),
        'release_ready':False}))
