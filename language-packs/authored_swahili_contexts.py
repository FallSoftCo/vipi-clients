#!/usr/bin/env python3
"""Swahili equivalents of the existing independent everyday authoring topics.

These exact contexts do not use AfriWOZ test text and do not create a dictionary
fallback. Discontinuous birthday/homework ownership is deliberately omitted.
Native locative -ni remains outside the explicitly scoped noun focus.
"""
import argparse
import json
from pathlib import Path
from authored_conversation import DATA as BASE, LANGUAGES, ARABIC_ARTICLES, marked, protocol
from authored_conversation_expansion import DATA as EXPANSION
from authored_conversation_routines import DATA as ROUTINES
from authored_everyday import mapping
from build_wiktextract import canonical, digest_file, readable_roman
from mapping_catalog import validate

SWAHILI = {
    'time_duration':'Ninahitaji [muda] zaidi.',
    'today':'Ninafanya kazi [leo].',
    'tomorrow':'Nitafanya kazi [kesho].',
    'yesterday':'Nilifanya kazi [jana].',
    'week':'Tutaonana [wiki] ijayo.',
    'month':'Nitahama [mwezi] ujao.',
    'year':'Tulihamia hapa [mwaka] jana.',
    'question':'Nina [swali].',
    'problem':'Kuna [tatizo].',
    'food':'Tunahitaji [chakula] zaidi.',
    'price':'[Bei] ni ya juu sana.',
    'family':'[Familia] yangu inaishi karibu.',
    'car':'[Gari] liko nje.',
    'book_reading':'Ninasoma [kitabu].',
    'message':'Nilituma [ujumbe].',
    'address':'[Anwani] ya hoteli ni ipi?',
    'station_rail':'Kiko wapi [kituo] cha treni?',
    'money':'Sina [pesa] za kutosha.',
    'help_noun':'Ninahitaji [msaada].',
    'work_job':'Ninatafuta [kazi].',
    'phone_device':'[Simu] inaita.',
    'friend_person':'[Rafiki] yangu yuko hapa.',
    'house_building':'[Nyumba] ina bustani.',
    'school_place':'[Shule] iko karibu na bustani.',
    'office_place':'Niko [ofisi]ni.',
    'meeting_event':'[Mkutano] unaanza adhuhuri.',
    'bus_vehicle':'[Basi] limechelewa.',
    'train_vehicle':'[Treni] imechelewa.',
    'ticket_rail':'Nilinunua [tiketi] ya treni.',
    'airport_place':'Tunaenda kwenye [uwanja wa ndege].',
    'hotel_place':'[Hoteli] iko karibu na uwanja wa ndege.',
    'room_interior':'[Chumba] cha hoteli ni tulivu.',
    'door_physical':'Tafadhali funga [mlango].',
    'key_door':'[Ufunguo] wa mlango uko wapi?',
    'bag_container':'[Mfuko] uko juu ya meza.',
    'breakfast_meal':'[Kifungua kinywa] kiko tayari.',
    'lunch_meal':'[Chakula cha mchana] kiko tayari.',
    'dinner_meal':'[Chakula cha jioni] kiko tayari.',
    'weather_conditions':'[Hali ya hewa] ni nzuri.',
    'rain_weather':'[Mvua] imekoma.',
    'morning_time':'Ninasoma [asubuhi].',
    'night_time':'Ninafanya kazi [usiku].',
    'weekend_days':'Nina nafasi [mwisho wa wiki] huu.',
    'class_session':'[Kipindi] kinaanza hivi karibuni.',
    'teacher_person':'[Mwalimu] anafafanua somo.',
    'student_person':'[Mwanafunzi] wa chuo kikuu anasoma kitabu.',
    'exam_school':'[Mtihani] wa shule ni kesho.',
    'home_residence':'Niko [nyumba]ni.',
    'email_message':'Nilituma [barua pepe].',
    'call_phone':'[Mazungumzo] ya simu yalikuwa mafupi.',
    'plan_arrangement':'[Mpango] wa safari ni upi?',
    'news_information':'Nina [habari] njema.',
    'movie_film':'Tulitazama [filamu].',
    'music_sound':'Ninasikiliza [muziki].',
    'photo_image':'Nilipiga [picha].',
    'party_event':'[Sherehe] ya siku ya kuzaliwa ni usiku wa leo.',
    'internet_network':'Muunganisho wa [intaneti] ni wa polepole.',
    'charger_device':'[Chaja] ya simu iko wapi?',
    'restaurant_place':'[Mkahawa] uko karibu na hoteli.',
}


def records():
    data = dict(BASE, **EXPANSION, **ROUTINES)
    if set(data)-set(SWAHILI) != {'birthday_day', 'homework_assignment'}:
        raise ValueError('Author explicitly assesses each added topic')
    for concept, swahili in SWAHILI.items():
        meaning, line = data[concept]
        forms = dict(zip(LANGUAGES, map(marked, line.split('|')), strict=True))
        forms['sw'] = marked(swahili)
        article = ARABIC_ARTICLES.get(concept)
        if article:
            sentence, old, _ = forms['ar']; word, reading = article
            if old != 'ال'+word: raise ValueError('Unexpected definite Arabic form')
            forms['ar'] = sentence, word, readable_roman(reading)
        for source, (original, left, _) in forms.items():
            for target, (translation, right, reading) in forms.items():
                if source == target or 'sw' not in (source, target): continue
                # Preserve the original batch's unresolved Chinese distinction
                # and Arabic attached ownership exclusions in the new pairs.
                if source == 'zh' and concept in ('question', 'problem'): continue
                if concept == 'family' and 'ar' in (source, target): continue
                row = mapping('swahili_context_'+concept, source, target, left, right,
                    original, translation, meaning, reading)
                row['usage']['context_generalization'] = 'exact authored sentence only'
                row['provenance']['priority_basis'] = 'Existing independent everyday topic batches; no reserved Swahili dialogue used'
                validate(row); yield row


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=False)
    rows = list(records())
    (args.output/'records.jsonl').write_text(''.join(canonical(row)+'\n' for row in rows))
    (args.output/'native-fixture.json').write_text(canonical({'schema':'vipi-reviewed-context-fixture-1',
        'synthetic_contexts':True, 'linguistic_acceptance':False,
        'records_sha256':digest_file(args.output/'records.jsonl'), 'rows':rows})+'\n')
    print(canonical({'records':len(rows), 'concepts':len(SWAHILI), 'pairs':20, 'release_ready':False}))
