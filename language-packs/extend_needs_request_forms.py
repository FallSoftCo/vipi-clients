#!/usr/bin/env python3
"""Explicit need/want/polite-request variants of the assessed noun contexts.

The complete reference remains a need sentence. Only its noun focus can be
reused in matched alternatives; subject, mood and tense are never transplanted.
No held-out text, inferred morphology or unrestricted noun fallback is used.
"""
import argparse
from copy import deepcopy
from pathlib import Path
import authored_needs_frames as base
from build_wiktextract import canonical, digest_file
from mapping_catalog import validate

BASE_SHA = '11db9924b33b43502060eaa4a2ef99f88fbca335b070d0b1e042e14887ed0e02'
FRENCH = dict(zip(base.DATA, ['de la ', 'de l’', 'de l’', 'de l’', 'des ', 'une ', 'un ', 'un ',
    'un ', 'un ', 'un ', 'un ', 'une ', 'un ', 'plus de ', 'du '], strict=True))
ITALIAN = dict(zip(base.DATA, ['del ', 'dell’', 'dei ', '', '', 'un ', 'un ', 'un ',
    'un ', 'una ', 'un ', 'un ', 'una ', 'una ', 'più ', 'del '], strict=True))


def variants(row, side, concept):
    language = row[side+'_language']; focus = row[side]
    span = row['usage'][side+'_frame_span']; frame = row[side+'_context'][span[0]:span[1]]
    a = frame.index(focus); before, after = frame[:a], frame[a+len(focus):]
    noun = {'focus': focus}
    literal = lambda value: [{'literal':value}] if value else []
    slot = lambda values: {'slot':sorted(set(values))}
    casing = lambda values: values + [v[0].upper()+v[1:] for v in values]
    if language == 'sw':
        result = deepcopy(row['usage'][side+'_frame_pattern'])
        for part in result:
            if part == {'literal':'hitaji '}: part.clear(); part.update(slot(['hitaji ', 'taka ']))
        return result
    verbs = {
        'en': ('need', ['need','needs','needed','want','wants','wanted','would like','would love','could use']),
        'es': ('Necesito', ['necesito','necesitas','necesita','necesitamos','necesitan','necesitar','necesitaba',
                            'quiero','quieres','quiere','queremos','quieren','quisiera','quisieran']),
        'de': ('brauche', ['brauche','brauchst','braucht','brauchen','brauchte','brauchten',
                           'möchte','möchtest','möchten','möchtet','hätte gern','hättest gern','hätten gern']),
    }
    if language in verbs:
        old, choices = verbs[language]; assert before.startswith(old)
        return [slot(casing([v+before[len(old):] for v in choices])), noun] + literal(after)
    if language == 'fr':
        choices = [before] + [verb+' '+FRENCH[concept] for verb in ['voudrais','voudrait','voudrions','voudraient','veux','veut','voulons','veulent']]
        return [slot(choices+[v.replace('’',"'") for v in choices]), noun] + literal(after)
    if language == 'it':
        choices = [before] + [verb+' '+ITALIAN[concept] for verb in ['vorrei','vorresti','vorrebbe','vorremmo','vorrebbero','voglio','vuole','vogliamo']]
        return [slot(choices+[v.replace('’',"'") for v in choices]), noun] + literal(after)
    if language == 'pt':
        assert before.startswith('Preciso de '); tail = before[len('Preciso de '):]
        choices = [v+' de '+tail for v in ['preciso','precisa','precisamos','precisam','precisar','precisava','gostaria','gostaríamos']]
        choices += [v+' '+tail for v in ['quero','quer','queremos','querem']]
        return [slot(casing(choices)), noun] + literal(after)
    if language == 'ar':
        return [slot([v+' إلى ' for v in ['أحتاج','تحتاج','يحتاج','نحتاج']] + [v+' ' for v in ['أريد','تريد','يريد','نريد','أود']]), noun] + literal(after)
    if language == 'zh':
        assert before.startswith('需要')
        return [slot([v+before[2:] for v in ['需要','想要','要']]), noun] + literal(after)
    if language == 'ja':
        return literal(before) + [noun, slot(['が必要です','が必要だ','が必要','が必要だった','が必要でした',
            'が欲しいです','が欲しい','がほしい','をください','をお願いします'])]
    if language == 'ko':
        assert after in ['이 필요해요','가 필요해요']
        particle = '을' if after.startswith('이') else '를'
        endings = [after.replace('필요해요',v) for v in ['필요해요','필요합니다','필요하다','필요했어요','필요한']]
        endings += [particle+' '+v for v in ['원해요','원합니다','원해','주세요']] + [' 주세요']
        return literal(before) + [noun, slot(endings)]
    raise ValueError('Unassessed language')


def records():
    if digest_file(Path(base.__file__)) != BASE_SHA: raise ValueError('Base authoring changed')
    for row in base.records():
        # mapping() retains the topic explicitly as its meaning identity.
        concept = next((key for key in base.DATA if row['logical_id'].startswith('vipi-authored-r1:needs_'+key+':')), None)
        if concept is None: raise ValueError('Unrecognized topic identity: '+row['logical_id'])
        for side in ('source','target'): row['usage'][side+'_frame_pattern'] = variants(row,side,concept)
        row['usage']['context_generalization'] = 'explicit finite need, want and polite-request constructions; complete reference unchanged'
        row['provenance']['priority_basis'] += '; independent extension of request forms, no evaluation wording'
        validate(row); yield row
        if 'sw' in (row['source_language'],row['target_language']) and not row['logical_id'].endswith(':sw-first-person-contraction'):
            alternate = deepcopy(row); alternate['logical_id'] += ':sw-polite-preference'
            side = 'source' if row['source_language']=='sw' else 'target'
            subjects = ['ni','u','a','tu','m','wa']
            prefixes = ['Ninahitaji '] + [subject+'ngependa ' for subject in subjects]
            prefixes += [value[0].upper()+value[1:] for value in prefixes]
            frame_span = row['usage'][side+'_frame_span']; frame = row[side+'_context'][frame_span[0]:frame_span[1]]
            suffix = frame[frame.index(row[side])+len(row[side]):]
            alternate['usage'][side+'_frame_pattern'] = [{'slot':sorted(set(prefixes))},{'focus':row[side]}] + ([{'literal':suffix}] if suffix else [])
            validate(alternate); yield alternate


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); a.output.mkdir(parents=True,exist_ok=False); rows=list(records()); path=a.output/'records.jsonl'
    path.write_text(''.join(canonical(row)+'\n' for row in rows))
    print(canonical({'records':len(rows),'records_sha256':digest_file(path),'authoring_source_sha256':digest_file(Path(__file__)),
                     'base_authoring_sha256':BASE_SHA,'release_ready':False}))
