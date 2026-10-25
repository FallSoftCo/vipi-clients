"""Conservative lexical evidence; a hint can veto, never certify a sense."""
from collections import defaultdict
from functools import lru_cache
import re
import sqlite3
import unicodedata
import json

HARAKAT = re.compile('[\u0640\u064b-\u0652\u0670]')
STOP = set('a an the of or and to in on at by for from with without into as is are be being that which who when where one someone something somebody person thing used use using type kind form sort any other particular specific especially usually often also such having relating pertaining certain act action process state make made its their this these those can may'.split())
GRAMMAR = {
    'en': set("not no never neither nor can could may might must shall should will would let's".split()),
    'es': set('no nunca ni tampoco jamás'.split()),
    'fr': set("ne n' pas jamais ni aucun".split()),
    'de': set('nicht nie kein keine keinen keinem keiner keines'.split()),
    'it': set('non mai né nessuno'.split()),
    'pt': set('não nunca nem jamais'.split()),
    'ar': set('لا لم لن ليس ليست لست ما'.split()),
    'zh': set('不 没 沒 没有 沒有 别 別 不要 不能 不会 不會 可以 能'.split()),
    'ja': set('ない ません ぬ ず ではない じゃない'.split()),
    'ko': set('안 못 아니다 없다 않다 말다'.split()),
}


def lookup_key(value, language):
    value = unicodedata.normalize('NFC', value).lower()
    return HARAKAT.sub('', value) if language == 'ar' else value


@lru_cache(maxsize=10)
def source_hint_lexicon(catalog, language):
    if language == 'en':
        return None
    words = defaultdict(set)
    with sqlite3.connect(catalog.resolve().as_uri() + '?mode=ro&immutable=1', uri=True) as db:
        db.create_function('has_scope', 1, has_scope, deterministic=True)
        scoped = {row[0] for row in db.execute('SELECT DISTINCT sense_id FROM terms WHERE language=? AND has_scope(qualifiers)', (language,))}
        for english, form, detail, sense_id in db.execute('''SELECT a.normalized,b.form,b.qualifiers,b.sense_id FROM terms a
            JOIN terms b ON a.sense_id=b.sense_id WHERE a.language='en' AND b.language=?''', (language,)):
            if sense_id in scoped or qualifier(detail) != '':
                continue
            if len(english) >= 3 and english not in STOP:
                value = lookup_key(form, language)
                if len(value) <= 64 and value not in GRAMMAR[language]:
                    words[english].add(value)
    return {key: sorted(value)[:4] for key, value in words.items()}


def hints(label, source_word, language, lexicon):
    words = list(dict.fromkeys(word for word in re.findall("[a-z][a-z'-]{2,}", label.lower())
                               if word not in STOP and word != source_word.lower()))[:8]
    values = words if lexicon is None else [value for word in words for value in lexicon.get(word, [])]
    return list(dict.fromkeys(values))[:24]


@lru_cache(maxsize=32768)
def qualifier(raw):
    value = json.loads(raw)
    if value.get('note') or value.get('raw_tags'):
        return None
    meanings = {re.sub(r'\belder\b', 'older', value[field].strip().lower())
                for field in ('english', 'translation') if value.get(field)}
    return next(iter(meanings)) if len(meanings) == 1 else '' if not meanings else None


def has_scope(raw):
    value = json.loads(raw)
    return bool(value.get('english') or value.get('translation'))


def qualifiers_compatible(a, b, source_word, source, target):
    left, right = qualifier(a), qualifier(b)
    if left is None or right is None:
        return False
    if left == right:
        return True
    # A generic English headword cannot supply an unstated age, speaker gender,
    # register or other restriction. Only an explicit headword phrase suffices.
    english = re.sub(r'\belder\b', 'older', source_word.lower())
    scoped = right if source == 'en' else left if target == 'en' else None
    return bool(scoped and re.search(r'(?<!\w)' + re.escape(scoped) + r'(?!\w)', english))
