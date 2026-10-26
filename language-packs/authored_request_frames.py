#!/usr/bin/env python3
"""Reusable requests and communication phrases, including Swahili.

Project-authored development evidence. No held-out dialogue supplies a string.
Person, tense, articles and negation outside the bracketed noun stay native.
Only finite, explicit constructions are indexed; no wildcard or stemmer.
"""
import argparse
from copy import deepcopy
from pathlib import Path
from authored_phrase_frames import parse
from authored_everyday import mapping
from build_wiktextract import canonical, digest_file
from mapping_catalog import validate

LANGUAGES = ('en', 'es', 'fr', 'de', 'it', 'pt', 'ar', 'zh', 'ja', 'ko', 'sw')
SEARCH = ('I am {f}.', 'Estoy {f}.', 'Je {f}.', 'Ich {f}.', 'Sto {f}.', 'Estou {f}.', '{f}.', '我在{f}。', '{f}。', '{f}.', '{f}.')
SEND = ('I am {f}.', 'Estoy {f}.', 'J’{f}.', 'Ich {f}.', 'Sto {f}.', 'Estou {f}.', '{f}.', '我正在{f}。', '{f}。', '{f}.', '{f}.')

DATA = {
    'restaurant_search': ('a restaurant sought as a place to eat', SEARCH,
        'looking for a [restaurant]|buscando un [restaurante]|cherche un [restaurant]|suche ein [Restaurant]|cercando un [ristorante]|procurando um [restaurante]|أبحث عن [مطعم~maṭ’am]|找[餐厅~cāntīng]|[レストラン~resutoran]を探しています|[식당~sikdang]을 찾고 있어요|Ninatafuta [mkahawa]'),
    'hotel_search': ('a hotel sought as accommodation', SEARCH,
        'looking for a [hotel]|buscando un [hotel]|cherche un [hôtel]|suche ein [Hotel]|cercando un [hotel]|procurando um [hotel]|أبحث عن [فندق~funduq]|找[酒店~jiǔdiàn]|[ホテル~hoteru]を探しています|[호텔~hotel]을 찾고 있어요|Ninatafuta [hoteli]'),
    'job_search': ('a job sought as employment, not a software process', SEARCH,
        'looking for a [job]|buscando un [trabajo]|cherche un [emploi]|suche eine [Stelle]|cercando un [lavoro]|procurando um [emprego]|أبحث عن [وظيفة~waẓīfa]|找[工作~gōngzuò]|[仕事~shigoto]を探しています|[일~il]을 찾고 있어요|Ninatafuta [kazi]'),
    'send_message': ('a message sent as interpersonal communication', SEND,
        'sending a [message]|enviando un [mensaje]|envoie un [message]|sende eine [Nachricht]|inviando un [messaggio]|enviando uma [mensagem]|أرسل [رسالة~risāla]|发[消息~xiāoxi]|[メッセージ~messēji]を送っています|[메시지~mesiji]를 보내고 있어요|Ninatuma [ujumbe]'),
    'send_email': ('an email sent as electronic mail, not a postal letter', SEND,
        'sending an [email]|enviando un [correo electrónico]|envoie un [e-mail]|sende eine [E-Mail]|inviando un’[email]|enviando um [e-mail]|أرسل [رسالة بريد إلكتروني~risālat barīd iliktrūnī]|发[电子邮件~diànzǐ yóujiàn]|[メール~mēru]を送っています|[이메일~imeil]을 보내고 있어요|Ninatuma [barua pepe]'),
    'train_ticket_request': ('a ticket for travel on a railway train',
        ('I {f}.', '{f}.', 'J’ai {f}.', 'Ich {f}.', '{f}.', '{f}.', '{f}.', '我{f}。', '{f}。', '{f}.', '{f}.'),
        'need a [train ticket]|Necesito un [billete de tren]|besoin d’un [billet de train]|brauche eine [Zugfahrkarte]|Mi serve un [biglietto del treno]|Preciso de uma [passagem de trem]|أحتاج إلى [تذكرة قطار~tadhkirat qiṭār]|需要一张[火车票~huǒchēpiào]|[列車の切符~ressha no kippu]が必要です|[기차표~gichapyo]가 필요해요|Ninahitaji [tiketi ya treni]'),
    'hotel_room_request': ('a room for accommodation in a hotel, not spare capacity',
        ('I {f}.', '{f}.', 'J’ai {f}.', 'Ich {f}.', '{f}.', '{f}.', '{f}.', '我{f}。', '{f}。', '{f}.', '{f}.'),
        'need a [hotel room]|Necesito una [habitación de hotel]|besoin d’une [chambre d’hôtel]|brauche ein [Hotelzimmer]|Mi serve una [camera d’albergo]|Preciso de um [quarto de hotel]|أحتاج إلى [غرفة فندق~ghurfat funduq]|需要一间[酒店房间~jiǔdiàn fángjiān]|[ホテルの部屋~hoteru no heya]が必要です|[호텔 방~hotel bang]이 필요해요|Ninahitaji [chumba cha hoteli]'),
}


def parts(concept, language, focus, frame):
    noun = {'focus': focus}
    slot = lambda values: {'slot': values}
    literal = lambda value: {'literal': value}
    searching = concept.endswith('_search')
    sending = concept in ('send_message', 'send_email')
    if searching:
        if language == 'en':
            return [slot([verb + article for verb in ('looking for ', 'searching for ', 'look for ', 'looks for ', 'find ')
                          for article in ('a ', 'the ')]), noun]
        if language == 'es': return [slot([verb + ' ' + article + ' ' for verb in ('buscando', 'busco', 'buscas', 'busca', 'buscamos', 'buscan', 'buscar') for article in ('un', 'el')]), noun]
        if language == 'fr':
            articles = ('un ', 'le ') if concept == 'restaurant_search' else ('un ', 'l’', "l'")
            return [slot([verb + ' ' + article for verb in ('cherche', 'cherches', 'cherchons', 'cherchez', 'cherchent', 'chercher') for article in articles]), noun]
        if language == 'de':
            articles = ('eine', 'die') if concept == 'job_search' else ('ein', 'das')
            return [slot([verb + ' ' + article + ' ' for verb in ('suche', 'suchst', 'sucht', 'suchen') for article in articles]), noun]
        if language == 'it': return [slot([verb + ' un ' for verb in ('cercando', 'cerco', 'cerchi', 'cerca', 'cerchiamo', 'cercate', 'cercano', 'cercare')]), noun]
        if language == 'pt': return [slot([verb + ' um ' for verb in ('procurando', 'procuro', 'procura', 'procuramos', 'procuram', 'procurar')]), noun]
        if language == 'ar': return [slot([verb + ' عن ' for verb in ('أبحث', 'نبحث', 'تبحث', 'يبحث')]), noun]
        if language == 'zh': return [slot(['找', '寻找', '找一家', '寻找一家'] if concept != 'job_search' else ['找', '寻找', '找一份', '寻找一份']), noun]
        if language == 'ja': return [noun, literal('を'), slot(['探しています', '探している', '探してる', '探します', '探す', '探していた', '探したい'])]
        if language == 'ko': return [noun, literal('을 '), slot(['찾고 있어요', '찾고 있다', '찾아요', '찾습니다', '찾는', '찾고', '찾았어요'])]
    if sending:
        if language == 'en':
            article = 'an ' if concept == 'send_email' else 'a '
            return [slot([verb + a for verb in ('sending ', 'send ', 'sends ', 'sent ') for a in (article, 'the ')]), noun]
        if language == 'es': return [slot([verb + ' un ' for verb in ('enviando', 'envío', 'envías', 'envía', 'enviamos', 'envían', 'enviar', 'envié')]), noun]
        if language == 'fr': return [slot([verb + ' un ' for verb in ('envoie', 'envoies', 'envoyons', 'envoyez', 'envoient', 'envoyer', 'envoyé')]), noun]
        if language == 'de': return [slot([verb + ' eine ' for verb in ('sende', 'sendest', 'sendet', 'senden', 'schicke', 'schickst', 'schickt', 'schicken')]), noun]
        if language == 'it':
            articles = (' un’', " un'") if concept == 'send_email' else (' un ',)
            return [slot([verb + article for verb in ('inviando', 'invio', 'invia', 'inviamo', 'inviano', 'inviare', 'inviato') for article in articles]), noun]
        if language == 'pt': return [slot([verb + (' um ' if concept == 'send_email' else ' uma ') for verb in ('enviando', 'envio', 'envia', 'enviamos', 'enviam', 'enviar', 'enviei')]), noun]
        if language == 'ar': return [slot([verb + ' ' for verb in ('أرسل', 'يرسل', 'ترسل', 'نرسل')]), noun]
        if language == 'zh': return [slot(['发', '发送', '发一封', '发送一封'] if concept == 'send_email' else ['发', '发送', '发一条', '发送一条']), noun]
        if language == 'ja': return [noun, literal('を'), slot(['送っています', '送っている', '送ります', '送る', '送った', '送りました'])]
        if language == 'ko': return [noun, literal('을 ' if concept == 'send_email' else '를 '), slot(['보내고 있어요', '보내고 있다', '보내요', '보냅니다', '보냈어요', '보내는'])]
    if concept.endswith('_request') and language == 'en':
        return [slot(['need a ', 'needs a ', 'needed a ', 'need the ', 'needs the ']), noun]
    if language == 'sw':
        verb = 'tafuta' if searching else 'tuma' if sending else 'hitaji'
        subjects = ['ni', 'u', 'a', 'tu', 'm', 'wa']
        return [slot(subjects + [s.capitalize() for s in subjects]), slot(['na', 'li', 'ta']), literal(verb + ' '), noun]
    a = frame.index(focus)
    return ([literal(frame[:a])] if a else []) + [noun] + ([literal(frame[a+len(focus):])] if a+len(focus) < len(frame) else [])


def records():
    for concept, (meaning, templates, marked) in DATA.items():
        forms = {}
        for language, template, phrase in zip(LANGUAGES, templates, marked.split('|'), strict=True):
            frame, focus, reading = parse(phrase)
            forms[language] = template.format(f=frame), frame, focus, reading
        for source, (original, left_frame, left, _) in forms.items():
            for target, (translation, right_frame, right, reading) in forms.items():
                if source == target: continue
                row = mapping('requests_' + concept, source, target, left, right, original, translation, meaning, reading)
                row['usage'].update(context_extent='local_phrase',
                    context_generalization='explicit finite conversational constructions',
                    source_frame_span=[original.index(left_frame), original.index(left_frame)+len(left_frame)],
                    target_frame_span=[translation.index(right_frame), translation.index(right_frame)+len(right_frame)],
                    permitted_context=meaning + '; surrounding person, tense, possession and negation remain unchanged.',
                    abstain_when=['Either construction is absent.', 'The relevant construction repeats ambiguously.', 'Meanings conflict.', 'Protected text overlaps the focus.'])
                row['usage']['source_frame_pattern'] = parts(concept, source, left, left_frame)
                row['usage']['target_frame_pattern'] = parts(concept, target, right, right_frame)
                row['provenance']['priority_basis'] = 'Independently authored everyday requests and communication, not held-out conversation wording'
                validate(row); yield row
                if 'sw' in (source, target):
                    # A second bounded construction covers common first-person
                    # contraction without inventing invalid subject/tense mixes.
                    # Both constructions retain the same complete reference.
                    alternate = deepcopy(row)
                    alternate['logical_id'] += ':sw-first-person-contraction'
                    side = 'source' if source == 'sw' else 'target'
                    verb = 'tafuta' if concept.endswith('_search') else 'tuma' if concept.startswith('send_') else 'hitaji'
                    alternate['usage'][side + '_frame_pattern'] = [
                        {'slot': ['Nina', 'nina', 'Na', 'na']}, {'literal': verb + ' '},
                        {'focus': alternate[side]}]
                    alternate['usage']['context_generalization'] = 'explicit finite constructions with common Swahili first-person present contraction'
                    validate(alternate); yield alternate


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); a.output.mkdir(parents=True, exist_ok=False)
    rows = list(records()); path = a.output/'records.jsonl'
    path.write_text(''.join(canonical(row)+'\n' for row in rows))
    print(canonical({'records':len(rows), 'concepts':len(DATA), 'pairs':110,
                     'records_sha256':digest_file(path), 'authoring_source_sha256':digest_file(Path(__file__)), 'release_ready':False}))
