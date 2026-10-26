#!/usr/bin/env python3
"""Finite everyday noun-request contexts across eleven languages.

Training-only frequency priorities informed topic selection. Sentences and
readings are newly authored, never copied from held-out dialogue. The noun is
the sole replaceable focus; articles, person, tense and quantity stay outside.
"""
import argparse
from copy import deepcopy
from pathlib import Path
from authored_phrase_frames import parse
from authored_everyday import mapping
from build_wiktextract import canonical, digest_file
from mapping_catalog import validate

LANGUAGES = ('en', 'es', 'fr', 'de', 'it', 'pt', 'ar', 'zh', 'ja', 'ko', 'sw')
TEMPLATES = ('I {f}.', '{f}.', 'J’ai {f}.', 'Ich {f}.', 'Ho {f}.', '{f}.', '{f}.', '我{f}。', '{f}。', '{f}.', '{f}.')
PRIORITY = 'f0f3314d21da2218ba063e5b50da8c4e32f6f284b0ed1c8bbfde54be040b76c2'

DATA = {
    'food': ('food for eating',
        'need [food]|Necesito [comida]|besoin de [nourriture]|brauche [Essen]|bisogno di [cibo]|Preciso de [comida]|أحتاج إلى [طعام~ṭaʿām]|需要[食物~shíwù]|[食べ物~tabemono]が必要です|[음식~eumsik]이 필요해요|Ninahitaji [chakula]'),
    'water': ('water as a substance, not the act of watering',
        'need [water]|Necesito [agua]|besoin d’[eau]|brauche [Wasser]|bisogno di [acqua]|Preciso de [água]|أحتاج إلى [ماء~māʾ]|需要[水~shuǐ]|[水~mizu]が必要です|[물~mul]이 필요해요|Ninahitaji [maji]'),
    'money': ('money needed as financial means',
        'need [money]|Necesito [dinero]|besoin d’[argent]|brauche [Geld]|bisogno di [soldi]|Preciso de [dinheiro]|أحتاج إلى [مال~māl]|需要[钱~qián]|[お金~okane]が必要です|[돈~don]이 필요해요|Ninahitaji [pesa]'),
    'help': ('assistance needed, noun rather than imperative verb',
        'need [help]|Necesito [ayuda]|besoin d’[aide]|brauche [Hilfe]|bisogno di [aiuto]|Preciso de [ajuda]|أحتاج إلى [مساعدة~musāʿada]|需要[帮助~bāngzhù]|[助け~tasuke]が必要です|[도움~doum]이 필요해요|Ninahitaji [msaada]'),
    'information': ('information needed, not breaking news or a greeting',
        'need [information]|Necesito [información]|besoin d’[informations]|brauche [Informationen]|bisogno di [informazioni]|Preciso de [informações]|أحتاج إلى [معلومات~maʿlūmāt]|需要[信息~xìnxī]|[情報~jōhō]が必要です|[정보~jeongbo]가 필요해요|Ninahitaji [taarifa]'),
    'address': ('a postal address for delivery, not a speech or computer memory address',
        'need a [mailing address]|Necesito una [dirección postal]|besoin d’une [adresse postale]|brauche eine [Postanschrift]|bisogno di un [indirizzo postale]|Preciso de um [endereço postal]|أحتاج إلى [عنوان بريدي~ʿunwān barīdī]|需要一个[邮寄地址~yóujì dìzhǐ]|[郵送先の住所~yūsōsaki no jūsho]が必要です|[우편 주소~upyeon juso]가 필요해요|Ninahitaji [anwani ya posta]'),
    'phone_number': ('a number used to call a telephone',
        'need a [phone number]|Necesito un [número de teléfono]|besoin d’un [numéro de téléphone]|brauche eine [Telefonnummer]|bisogno di un [numero di telefono]|Preciso de um [número de telefone]|أحتاج إلى [رقم هاتف~raqam hātif]|需要一个[电话号码~diànhuà hàomǎ]|[電話番号~denwa bangō]が必要です|[전화번호~jeonhwabeonho]가 필요해요|Ninahitaji [nambari ya simu]'),
    'taxi': ('a taxi vehicle or its transport service',
        'need a [taxi]|Necesito un [taxi]|besoin d’un [taxi]|brauche ein [Taxi]|bisogno di un [taxi]|Preciso de um [táxi]|أحتاج إلى [سيارة أجرة~sayyārat ujra]|需要一辆[出租车~chūzūchē]|[タクシー~takushī]が必要です|[택시~taeksi]가 필요해요|Ninahitaji [teksi]'),
    'doctor': ('a medical practitioner needed for care, not an academic title',
        'need a [doctor]|Necesito un [médico]|besoin d’un [médecin]|brauche einen [Arzt]|bisogno di un [medico]|Preciso de um [médico]|أحتاج إلى [طبيب~ṭabīb]|需要一位[医生~yīshēng]|[医師~ishi]が必要です|[의사~uisa]가 필요해요|Ninahitaji [daktari]'),
    'receipt': ('a purchase receipt, not the act of receiving',
        'need a [receipt]|Necesito un [recibo]|besoin d’un [reçu]|brauche eine [Quittung]|bisogno di una [ricevuta]|Preciso de um [recibo]|أحتاج إلى [إيصال~īṣāl]|需要一张[收据~shōujù]|[領収書~ryōshūsho]が必要です|[영수증~yeongsujeung]이 필요해요|Ninahitaji [risiti]'),
    'phone_charger': ('an electrical charger for a phone',
        'need a [phone charger]|Necesito un [cargador de teléfono]|besoin d’un [chargeur de téléphone]|brauche ein [Handyladegerät]|bisogno di un [caricabatterie per il telefono]|Preciso de um [carregador de telefone]|أحتاج إلى [شاحن هاتف~shāḥin hātif]|需要一个[手机充电器~shǒujī chōngdiànqì]|[携帯電話の充電器~keitai denwa no jūdenki]が必要です|[휴대폰 충전기~hyudaepon chungjeongi]가 필요해요|Ninahitaji [chaja ya simu]'),
    'umbrella': ('a handheld umbrella for shelter from rain',
        'need an [umbrella]|Necesito un [paraguas]|besoin d’un [parapluie]|brauche einen [Regenschirm]|bisogno di un [ombrello]|Preciso de um [guarda-chuva]|أحتاج إلى [مظلة~miẓalla]|需要一把[雨伞~yǔsǎn]|[傘~kasa]が必要です|[우산~usan]이 필요해요|Ninahitaji [mwavuli]'),
    'door_key': ('a physical key for a door, not an encryption key or solution',
        'need a [door key]|Necesito una [llave de la puerta]|besoin d’une [clé de porte]|brauche einen [Türschlüssel]|bisogno di una [chiave della porta]|Preciso de uma [chave da porta]|أحتاج إلى [مفتاح باب~miftāḥ bāb]|需要一把[门钥匙~mén yàoshi]|[ドアの鍵~doa no kagi]が必要です|[문 열쇠~mun yeolsoe]가 필요해요|Ninahitaji [ufunguo wa mlango]'),
    'breakfast': ('the morning meal',
        'need [breakfast]|Necesito [desayuno]|besoin d’un [petit-déjeuner]|brauche ein [Frühstück]|bisogno di una [colazione]|Preciso de [café da manhã]|أحتاج إلى [فطور~fuṭūr]|需要[早餐~zǎocān]|[朝食~chōshoku]が必要です|[아침 식사~achim siksa]가 필요해요|Ninahitaji [kifungua kinywa]'),
    'time': ('more available time or duration, not the current clock reading',
        'need more [time]|Necesito más [tiempo]|besoin de plus de [temps]|brauche mehr [Zeit]|bisogno di più [tempo]|Preciso de mais [tempo]|أحتاج إلى [وقت~waqt] إضافي|需要更多[时间~shíjiān]|もっと[時間~jikan]が必要です|더 많은 [시간~sigan]이 필요해요|Ninahitaji [muda] zaidi'),
    'rest': ('a period of rest or relaxation, not a remainder',
        'need some [rest]|Necesito [descanso]|besoin de [repos]|brauche [Erholung]|bisogno di [riposo]|Preciso de [descanso]|أحتاج إلى [راحة~rāḥa]|需要[休息~xiūxi]|[休息~kyūsoku]が必要です|[휴식~hyusik]이 필요해요|Ninahitaji [mapumziko]'),
}


def pattern(language, frame, focus):
    a = frame.index(focus)
    before, after = frame[:a], frame[a+len(focus):]
    noun = {'focus': focus}
    literal = lambda value: [{'literal': value}] if value else []
    if language == 'sw':
        subjects = ['ni', 'u', 'a', 'tu', 'm', 'wa']
        return [{'slot': subjects + [s.capitalize() for s in subjects]}, {'slot': ['na', 'li', 'ta']},
                {'literal': 'hitaji '}, noun] + literal(after)
    verbs = {
        'en': ('need', ['need', 'needs', 'needed']),
        'es': ('Necesito', ['Necesito', 'necesito', 'necesitas', 'necesita', 'necesitamos', 'necesitan', 'necesitar', 'necesitaba']),
        'de': ('brauche', ['brauche', 'brauchst', 'braucht', 'brauchen', 'brauchte', 'brauchten']),
        'pt': ('Preciso', ['Preciso', 'preciso', 'precisa', 'precisamos', 'precisam', 'precisar', 'precisava']),
        'ar': ('أحتاج', ['أحتاج', 'تحتاج', 'يحتاج', 'نحتاج']),
    }
    if language in verbs:
        old, choices = verbs[language]
        assert before.startswith(old)
        return [{'slot': choices}] + literal(before[len(old):]) + [noun] + literal(after)
    if language == 'fr':
        return [{'slot': sorted(set([before, before.replace('’', "'")]))}, noun] + literal(after)
    if language == 'ja':
        assert after == 'が必要です'
        return literal(before) + [noun, {'slot': ['が必要です', 'が必要だ', 'が必要', 'が必要だった', 'が必要でした']}]
    if language == 'ko':
        assert after.endswith('필요해요')
        return literal(before) + [noun, {'slot': [after.replace('필요해요', v) for v in ('필요해요', '필요합니다', '필요하다', '필요했어요', '필요한')]}]
    return literal(before) + [noun] + literal(after)


def records():
    for concept, (meaning, line) in DATA.items():
        forms = {}
        for language, template, marked in zip(LANGUAGES, TEMPLATES, line.split('|'), strict=True):
            frame, focus, reading = parse(marked)
            forms[language] = template.format(f=frame), frame, focus, reading
        for source, (original, left_frame, left, _) in forms.items():
            for target, (translation, right_frame, right, reading) in forms.items():
                if source == target: continue
                row = mapping('needs_' + concept, source, target, left, right, original, translation, meaning, reading)
                row['usage'].update(context_extent='local_phrase',
                    context_generalization='finite independently assessed noun-request constructions',
                    source_frame_span=[original.index(left_frame), original.index(left_frame)+len(left_frame)],
                    target_frame_span=[translation.index(right_frame), translation.index(right_frame)+len(right_frame)],
                    source_frame_pattern=pattern(source, left_frame, left),
                    target_frame_pattern=pattern(target, right_frame, right),
                    permitted_context=meaning + '; person, tense, articles, negation and quantity outside the focus are preserved.',
                    abstain_when=['Either assessed construction is absent.', 'A construction repeats with uncertain alignment.',
                                  'The focus overlaps protected text.', 'Competing meanings or readings disagree.'])
                row['provenance']['priority_basis'] = 'Training-only Swahili frequency queue ' + PRIORITY + '; independently authored everyday needs, no held-out wording'
                validate(row); yield row
                if 'sw' in (source, target):
                    alternate = deepcopy(row); alternate['logical_id'] += ':sw-first-person-contraction'
                    side = 'source' if source == 'sw' else 'target'
                    old = alternate['usage'][side + '_frame_pattern']
                    alternate['usage'][side + '_frame_pattern'] = [{'slot': ['Nina', 'nina', 'Na', 'na']}, {'literal': 'hitaji '}] + old[3:]
                    validate(alternate); yield alternate


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); a.output.mkdir(parents=True, exist_ok=False)
    rows = list(records()); path = a.output/'records.jsonl'
    path.write_text(''.join(canonical(row)+'\n' for row in rows))
    print(canonical({'records':len(rows), 'concepts':len(DATA), 'pairs':110,
        'records_sha256':digest_file(path), 'authoring_source_sha256':digest_file(Path(__file__)), 'release_ready':False}))
