#!/usr/bin/env python3
"""Explicit plural noun counterparts for already assessed everyday concepts.

The pinned previous catalog supplies only existing sense identities and exact
readings for unchanged native forms. No dictionary, evaluation utterance,
stemmer or language model supplies runtime morphology.
"""
import argparse
import json
from pathlib import Path
import sqlite3

import authored_conversation as base
import authored_conversation_expansion as expansion
import authored_conversation_routines as routines
from authored_everyday import mapping
from authored_everyday_units import MEANINGS as EXISTING_MEANINGS
from authored_people_ideas_units import LANGUAGES, forms
from build_wiktextract import canonical, digest_file
from mapping_catalog import validate

BASELINE_SHA = 'd0ca733215b084617055ca0ebb50a8c7477837bb89999b3605edd0c1b040a7c7'
# A slash lists alternatives explicitly. Number-unmarked nouns are intentionally
# valid counterparts only when the actual full translation contains that form.
DATA = {
 'friend_person': 'friends|amigos|amis|Freunde|amici|amigos|أصدقاء~aṣdiqāʾ|朋友~péngyou/朋友们~péngyoumen|友達~tomodachi|친구들~chingudeul/친구~chingu|marafiki',
 'phone_device': 'phones|teléfonos|téléphones|Telefone|telefoni|telefones|هواتف~hawātif|电话~diànhuà|電話~denwa|전화~jeonhwa|simu',
 'house_building': 'houses|casas|maisons|Häuser|case|casas|بيوت~buyūt/منازل~manāzil|房子~fángzi|家~ie|집들~jipdeul/집~jip|nyumba',
 'school_place': 'schools|escuelas|écoles|Schulen|scuole|escolas|مدارس~madāris|学校~xuéxiào|学校~gakkō|학교들~hakgyodeul/학교~hakgyo|shule',
 'office_place': 'offices|oficinas|bureaux|Büros|uffici|escritórios|مكاتب~makātib|办公室~bàngōngshì|オフィス~ofisu|사무실들~samusildeul/사무실~samusil|ofisi',
 'meeting_event': 'meetings|reuniones|réunions|Treffen|riunioni|reuniões|اجتماعات~ijtimāʿāt|会议~huìyì|会議~kaigi|회의들~hoe-uideul/회의~hoe-ui|mikutano',
 'bus_vehicle': 'buses|autobuses|bus|Busse|autobus|ônibus|حافلات~ḥāfilāt|公交车~gōngjiāochē|バス~basu|버스들~beoseudeul/버스~beoseu|mabasi',
 'train_vehicle': 'trains|trenes|trains|Züge|treni|trens|قطارات~qiṭārāt|火车~huǒchē|電車~densha|기차들~gichadeul/기차~gicha|treni',
 'airport_place': 'airports|aeropuertos|aéroports|Flughäfen|aeroporti|aeroportos|مطارات~maṭārāt|机场~jīchǎng|空港~kūkō|공항들~gonghangdeul/공항~gonghang|viwanja vya ndege',
 'hotel_place': 'hotels|hoteles|hôtels|Hotels|alberghi|hotéis|فنادق~fanādiq|酒店~jiǔdiàn|ホテル~hoteru|호텔들~hoteldeul/호텔~hotel|hoteli',
 'door_physical': 'doors|puertas|portes|Türen|porte|portas|أبواب~abwāb|门~mén|ドア~doa|문들~mundeul/문~mun|milango',
 'teacher_person': 'teachers|profesores|enseignants|Lehrer|insegnanti|professores|معلمون~muʿallimūn/معلمين~muʿallimīn|老师~lǎoshī/老师们~lǎoshīmen|先生~sensei/先生たち~senseitachi|선생님들~seonsaengnimdeul/선생님~seonsaengnim|walimu',
 'student_person': 'students|estudiantes|étudiants|Studenten|studenti|estudantes|طلاب~ṭullāb|学生~xuésheng/学生们~xuéshengmen|学生~gakusei/学生たち~gakuseitachi|학생들~haksaengdeul/학생~haksaeng|wanafunzi',
 'email_message': 'emails|correos electrónicos|courriels|E-Mails|email|e-mails|رسائل إلكترونية~rasāʾil iliktrūniyya|电子邮件~diànzǐ yóujiàn|メール~mēru|이메일들~imeildeul/이메일~imeil|barua pepe',
 'movie_film': 'movies|películas|films|Filme|film|filmes|أفلام~aflām|电影~diànyǐng|映画~eiga|영화들~yeonghwadeul/영화~yeonghwa|filamu',
 'photo_image': 'photos|fotos|photos|Fotos|foto|fotos|صور~ṣuwar|照片~zhàopiàn|写真~shashin|사진들~sajindeul/사진~sajin|picha',
 'restaurant_place': 'restaurants|restaurantes|restaurants|Restaurants|ristoranti|restaurantes|مطاعم~maṭāʿim|餐厅~cāntīng|レストラン~resutoran|식당들~sikdangdeul/식당~sikdang|migahawa',
 'reading_book': 'books|libros|livres|Bücher|libri|livros|كتب~kutub|书~shū|本~hon|책들~chaekdeul/책~chaek|vitabu',
 'car': 'cars|coches|voitures|Autos|auto|carros|سيارات~sayyārāt|汽车~qìchē|車~kuruma|자동차들~jadongchadeul/자동차~jadongcha|magari',
 'question': 'questions|preguntas|questions|Fragen|domande|perguntas|أسئلة~asʾila|问题~wèntí|質問~shitsumon|질문들~jilmundeul/질문~jilmun|maswali',
 'problem': 'problems|problemas|problèmes|Probleme|problemi|problemas|مشكلات~mushkilāt|问题~wèntí|問題~mondai|문제들~munjedeul/문제~munje|matatizo',
 'plan_arrangement': 'plans|planes|plans|Pläne|piani|planos|خطط~khuṭaṭ|计划~jìhuà|計画~keikaku|계획들~gyehoekdeul/계획~gyehoek|mipango',
 'bag_container': 'bags|bolsas|sacs|Taschen|borse|sacolas|حقائب~ḥaqāʾib|袋子~dàizi|袋~fukuro|가방들~gabangdeul/가방~gabang|mifuko',
 'year': 'years|años|années|Jahre|anni|anos|سنوات~sanawāt|年~nián|年~nen|년~nyeon|miaka',
 'week': 'weeks|semanas|semaines|Wochen|settimane|semanas|أسابيع~asābīʿ|周~zhōu|週~shū|주~ju|wiki',
 'month': 'months|meses|mois|Monate|mesi|meses|أشهر~ashhur|月~yuè|月~tsuki|개월~gaewol|miezi',
}
# These written forms can independently be a verb, adjective or another assessed
# meaning. Keep target availability; source use needs a separately assessed frame.
EXCLUDED_SOURCES = {
 ('zh','question'), ('zh','problem'),
 ('ar','reading_book'), ('ar','photo_image'), ('ar','plan_arrangement'), ('ar','month'),
 ('en','reading_book'), ('en','plan_arrangement'), ('en','train_vehicle'),
 ('en','school_place'), ('en','house_building'), ('en','question'), ('en','email_message'),
}


def baseline_readings(directory):
    if digest_file(directory/'catalog.json') != BASELINE_SHA:
        raise ValueError('Changed baseline catalog')
    catalog = json.loads((directory/'catalog.json').read_text())
    readings = {}
    for entry in catalog['packs']:
        path = directory/(entry['id']+'.sqlite')
        if digest_file(path) != entry['sha256']: raise ValueError('Changed baseline database')
        with sqlite3.connect('file:'+str(path.resolve())+'?mode=ro', uri=True) as db:
            for payload, in db.execute('SELECT payload FROM mappings'):
                row=json.loads(payload)
                if row.get('lexical_unit') and row['reading']:
                    key=(row['target_language'],row['target'],row['meaning'])
                    readings.setdefault(key,set()).add(row['reading'])
    if any(len(values)!=1 for values in readings.values()):
        raise ValueError('Unresolved baseline reading for an identical native form and meaning')
    return {key: next(iter(values)) for key,values in readings.items()}


def records(readings):
    existing=dict(base.DATA,**expansion.DATA,**routines.DATA)
    for topic,line in DATA.items():
        meaning=EXISTING_MEANINGS.get(topic) or existing[topic][0]
        parsed={lang:forms(cell,lang) for lang,cell in zip(LANGUAGES,line.split('|'),strict=True)}
        for source,lefts in parsed.items():
            if (source,topic) in EXCLUDED_SOURCES: continue
            for target,rights in parsed.items():
                if source==target: continue
                for li,(left,_) in enumerate(lefts):
                    for ri,(right,reading) in enumerate(rights):
                        reading=readings.get((target,right,meaning),reading)
                        row=mapping('plural_unit_'+topic,source,target,left,right,left,right,meaning,reading)
                        row['logical_id']+=':'+str(li)+':'+str(ri)
                        row['usage'].update(context_extent='local_phrase',lexical_unit=True,whole_reference=False,
                            context_generalization='explicit complete plural noun counterpart; no inferred inflection',number_group='plural',
                            source_frame_span=row['source_span'][:],target_frame_span=row['target_span'][:],
                            source_frame_pattern=[{'focus':left}],target_frame_pattern=[{'focus':right}],
                            permitted_context=meaning+'; both complete unique counterparts must occur in the actual whole translation',
                            abstain_when=['Missing or repeated complete native counterpart.',
                                'Competing meanings/readings, protected literals or invalid native boundaries.',
                                'Unlisted articles, possessors, conjugations or inflections receive no inferred permission.'])
                        row['provenance'].update(priority_basis='Explicit plural forms of previously authored everyday concepts. No evaluation utterance read.',
                            form_source='Project-authored explicit forms; no automatic morphology or dictionary promotion',
                            number_scope='Plural semantic group only; some listed native nouns leave grammatical number unmarked',
                            baseline_readings_catalog_sha256=BASELINE_SHA,
                            whole_reference_eligibility='False: noun carrier is not a whole-message translation')
                        validate(row);yield row


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();rows=list(records(baseline_readings(args.baseline)))
    assert len(rows)==len({r['logical_id'] for r in rows})
    args.output.mkdir(parents=True,exist_ok=False)
    path=args.output/'records.jsonl';path.write_text(''.join(canonical(r)+'\n' for r in rows))
    print(canonical({'records':len(rows),'concepts':len(DATA),'records_sha256':digest_file(path),
        'authoring_source_sha256':digest_file(Path(__file__)),'author_assessment_pending':True,'release_ready':False}))
