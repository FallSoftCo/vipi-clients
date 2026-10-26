#!/usr/bin/env python3
"""Bounded Swahili constructions in both directions with the original ten languages.

Project-authored development data, not independent linguistic acceptance.
The surrounding grammar stays outside the lexical focus. Finite person and
tense alternatives are explicit strings, never inferred stems or wildcards.
"""
import argparse
import json
from pathlib import Path
from authored_phrase_frames import DATA, parse, pattern
from authored_conversation import LANGUAGES, protocol
from authored_everyday import mapping
from build_wiktextract import canonical, digest_file
from mapping_catalog import validate

SWAHILI = {
    'reading_book': ('{f} sasa.', 'Ninasoma [kitabu]', 'soma'),
    'drinking_water': ('{f} sasa.', 'Ninakunywa [maji]', 'kunywa'),
    'birthday_party': ('{f} ni kesho.', '[Sherehe] ya siku ya kuzaliwa', None),
    'phone_charger': ('Iko wapi {f}?', '[chaja] ya simu', None),
    'drinking_coffee': ('{f} sasa.', 'Ninakunywa [kahawa]', 'kunywa'),
    'drinking_tea': ('{f} sasa.', 'Ninakunywa [chai]', 'kunywa'),
    'eating_bread': ('{f} sasa.', 'Ninakula [mkate]', 'kula'),
    'eating_cheese': ('{f} sasa.', 'Ninakula [jibini]', 'kula'),
    'listening_music': ('{f} sasa.', 'Ninasikiliza [muziki]', 'sikiliza'),
    'watching_movie': ('{f} sasa.', 'Ninatazama [filamu]', 'tazama'),
    'playing_piano': ('{f} sasa.', 'Ninapiga [piano]', 'piga'),
    'walking_dog': ('{f} sasa.', 'Ninamtembeza [mbwa]', 'mtembeza'),
    'bank_account': ('Nina {f}.', '[akaunti] ya benki', None),
    'train_station': ('{f}?', 'Kiko wapi [kituo cha treni]', None),
    'bus_stop': ('{f}?', 'Kiko wapi [kituo cha basi]', None),
    'phone_number': ('{f} ni ipi?', '[Nambari ya simu] yako', None),
    'liking_music': ('{f}.', 'Ninapenda [muziki]', 'penda'),
    'possessed_dog': ('Niko pamoja na {f}.', '[mbwa] wangu', None),
}

def swahili_pattern(concept, focus):
    verb = SWAHILI[concept][2]
    if verb:
        subjects = ['ni', 'u', 'a', 'tu', 'm', 'wa']
        return [{'slot': subjects + [s.capitalize() for s in subjects]},
                {'slot': ['na', 'li', 'ta']}, {'literal': verb + ' '}, {'focus': focus}]
    if concept == 'possessed_dog':
        return [{'focus': focus}, {'literal': ' '},
                {'slot': ['wangu', 'wako', 'wake', 'wetu', 'wenu', 'wao']}]
    return None

def records():
    for concept, (meaning, templates, frames) in DATA.items():
        sw_template, sw_marked, _ = SWAHILI[concept]
        forms = {}
        for language, template, marked in zip((*LANGUAGES, 'sw'), [*templates, sw_template], [*frames, sw_marked], strict=True):
            frame, focus, reading = parse(marked)
            forms[language] = (template.format(f=frame), frame, focus, reading)
        for source, (original, left_frame, left, _) in forms.items():
            for target, (translation, right_frame, right, reading) in forms.items():
                if source == target or 'sw' not in (source, target): continue
                row = mapping('phrase_frame_' + concept, source, target, left, right, original, translation, meaning, reading)
                row['usage'].update(context_extent='local_phrase',
                    context_generalization='explicit literal phrase in a larger message',
                    source_frame_span=[original.index(left_frame), original.index(left_frame)+len(left_frame)],
                    target_frame_span=[translation.index(right_frame), translation.index(right_frame)+len(right_frame)],
                    permitted_context='Literal ' + meaning + '. Person, tense, negation and ownership outside the focus remain unchanged.',
                    abstain_when=['A source or target construction is absent.', 'A corresponding construction repeats ambiguously.',
                                  'Records conflict in meaning.', 'Protected text overlaps the focus or a required reading is absent.'])
                row['provenance']['priority_basis'] = 'Swahili expansion of eighteen existing everyday constructions; no reserved conversations used'
                for side, language, word in [('source', source, left), ('target', target, right)]:
                    parts = swahili_pattern(concept, word) if language == 'sw' else pattern(concept, language, word)
                    if parts is not None: row['usage'][side + '_frame_pattern'] = parts
                validate(row)
                yield row

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    rows = list(records())
    (args.output/'records.jsonl').write_text(''.join(canonical(row)+'\n' for row in rows))
    probe = protocol(rows)
    probe.update(qa_run_id='013', scope='Authored Swahili development constructions; not held-out acceptance')
    (args.output/'phrase-protocol.json').write_text(json.dumps(probe, ensure_ascii=False, indent=2)+'\n')
    (args.output/'native-fixture.json').write_text(canonical({'schema':'vipi-reviewed-frame-fixture-1',
        'synthetic_contexts':True, 'linguistic_acceptance':False,
        'records_sha256':digest_file(args.output/'records.jsonl'), 'rows':rows})+'\n')
    print(canonical({'records':len(rows), 'concepts':len(SWAHILI), 'pairs':20, 'release_ready':False}))
