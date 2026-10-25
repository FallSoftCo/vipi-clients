#!/usr/bin/env python3
"""Build a research-only local search index of attested aligned examples.

Only explicit, bounded source/translation spans from the pinned dictionary are
used. This does not invent word alignment, equate a search hit with acceptance,
or turn generated/held-out test text into dictionary evidence.
"""
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import re
import sqlite3
import time
import unicodedata
from urllib.parse import quote

from build_wiktextract import LANGUAGES, EXCLUDED, clean, digest_file, form_ok, readable_roman, MAX_LINE
from context_hints import lookup_key, native_grammar

SCHEMA = '''
PRAGMA journal_mode=DELETE;
PRAGMA temp_store=FILE;
PRAGMA cache_size=-8192;
CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE examples(id INTEGER PRIMARY KEY,source_language TEXT NOT NULL,target_language TEXT NOT NULL,
 source TEXT NOT NULL,source_key TEXT NOT NULL,target TEXT NOT NULL,reading TEXT NOT NULL,
 source_context TEXT NOT NULL,target_context TEXT NOT NULL,gloss TEXT NOT NULL,tags TEXT NOT NULL,
 source_line INTEGER NOT NULL,source_url TEXT NOT NULL,headword TEXT NOT NULL,
 sense_index INTEGER NOT NULL,example_index INTEGER NOT NULL,search_text TEXT NOT NULL,
 source_start INTEGER NOT NULL,source_end INTEGER NOT NULL,
 target_start INTEGER NOT NULL,target_end INTEGER NOT NULL,
 usage_evidence TEXT NOT NULL);
CREATE INDEX example_lookup ON examples(source_language,target_language,source_key);
CREATE VIRTUAL TABLE context_search USING fts4(search_text,content='examples',tokenize=unicode61 'remove_diacritics=0');
'''


def search_text(text, language):
    text = lookup_key(text, language)
    if language not in ('zh', 'ja'): return text
    # Unicode61 alone treats an unspaced CJK sentence as one token. Keep
    # character bigrams for retrieval; these never assert word boundaries.
    runs = []; buffer = ''; previous = None
    for char in text:
        kind = 'cjk' if re.fullmatch(r'[\u3040-\u30ff\u3400-\u9fff\U00020000-\U0002ffff]', char) else 'word' if unicodedata.category(char)[0] in ('L', 'M') else None
        if kind != previous or kind is None:
            if buffer: runs.append((previous, buffer))
            buffer = ''
        if kind: buffer += char
        previous = kind
    if buffer: runs.append((previous, buffer))
    result = []
    for kind, run in runs:
        if kind == 'cjk': result.extend(run[i:i+2] for i in range(len(run)-1))
        else: result.append(run)
    return ' '.join(result)


def focus(text, offsets):
    if not isinstance(text, str) or not 0 < len(text) <= 2048 or not isinstance(offsets, list) or len(offsets) != 1: return None
    span = offsets[0]
    if not isinstance(span, list) or len(span) != 2 or any(type(x) is not int for x in span): return None
    start, end = span
    if not 0 <= start < end <= len(text): return None
    value = text[start:end]
    return value if value == clean(value) and form_ok(value) else None


def records(entry, line, counts, grammar=None):
    language = entry.get('lang_code')
    if language not in LANGUAGES or language == 'en' or set(entry.get('tags', [])) & EXCLUDED: return
    headword = clean(entry.get('word', ''))
    if not form_ok(headword): return
    for sense_index, sense in enumerate(entry.get('senses', [])):
        if set(sense.get('tags', [])) & (EXCLUDED | {'form-of', 'alt-of'}): continue
        gloss = ' / '.join(sense.get('glosses', []))[:2048]
        for example_index, example in enumerate(sense.get('examples', [])):
            counts['examples_seen_' + language] += 1
            # Quoted works retain their own rights. This pilot uses only entries
            # explicitly labelled usage examples, without an external reference.
            if example.get('type') != 'example' or example.get('ref'):
                counts['not_plain_usage_example'] += 1; continue
            native = example.get('text'); english = example.get('english') or example.get('translation')
            source = focus(native, example.get('bold_text_offsets'))
            target = focus(english, example.get('bold_translation_offsets'))
            if not source or not target:
                counts['missing_or_unsupported_explicit_alignment'] += 1; continue
            if source.casefold() == target.casefold(): continue
            # An explicitly marked romanization span belongs to this example's
            # target form. Never generate a reading from unrelated characters
            # or reuse an entire sentence's romanization as a word's reading.
            roman_focus = focus(example.get('roman'), example.get('bold_roman_offsets'))
            native_reading = readable_roman(roman_focus) if roman_focus else ''
            common = {'gloss': gloss, 'tags': json.dumps(sense.get('tags', []), ensure_ascii=False),
                      'source_line': line, 'source_url': 'https://en.wiktionary.org/wiki/' + quote(headword, safe='') + '#' + quote(entry.get('lang', language), safe=''),
                      'headword': headword, 'sense_index': sense_index, 'example_index': example_index}
            # Retain source grammatical/register evidence without guessing the
            # English focus's POS from the other language's headword. Native
            # tags describe the entry/sense/example, not a certified bilingual
            # permission to reuse the inflected span in another sentence.
            usage = {'native_language':language,'native_part_of_speech':entry.get('pos'),
                     'entry_tags':entry.get('tags',[]),'entry_raw_tags':entry.get('raw_tags',[]),
                     'sense_tags':sense.get('tags',[]),'sense_raw_tags':sense.get('raw_tags',[]),
                     'sense_topics':sense.get('topics',[]),
                     'example_tags':example.get('tags',[]),'example_raw_tags':example.get('raw_tags',[]),
                     'context_conditions':'not_inferred'}
            for s, t, a, b, context, translated_context in [(language, 'en', source, target, native, english),
                                                         ('en', language, target, source, english, native)]:
                if native_grammar(a, s, grammar[s] if grammar else ()):
                    counts['grammar_excluded'] += 1; continue
                yield dict(common, source_language=s, target_language=t, source=a, source_key=lookup_key(a, s),
                           target=b, reading=native_reading if s == 'en' and t in ('ar','zh','ja','ko') else '', source_context=context, target_context=translated_context,
                           search_text=search_text(context, s),
                           source_start=example['bold_text_offsets' if s == language else 'bold_translation_offsets'][0][0],
                           source_end=example['bold_text_offsets' if s == language else 'bold_translation_offsets'][0][1],
                           target_start=example['bold_translation_offsets' if s == language else 'bold_text_offsets'][0][0],
                           target_end=example['bold_translation_offsets' if s == language else 'bold_text_offsets'][0][1],
                           usage_evidence=json.dumps(usage,ensure_ascii=False,sort_keys=True))


def main(args):
    pinned = json.loads((Path(__file__).parent / 'sources/wiktextract-20261021.json').read_text())
    if args.source.stat().st_size != pinned['selection_bytes'] or digest_file(args.source) != pinned['selection_sha256']:
        raise ValueError('Pinned selected source required')
    args.output.mkdir(parents=True, exist_ok=False)
    path = args.output / 'contexts.sqlite'; counts = Counter(); start = time.monotonic()
    db = sqlite3.connect(path); db.executescript(SCHEMA)
    grammar = json.loads(args.grammar_guard.read_text())
    assert grammar['source_sha256'] == pinned['source_sha256']
    try:
        with gzip.open(args.source, 'rb') as stream:
            line = 0
            while raw := stream.readline(MAX_LINE + 1):
                if len(raw) > MAX_LINE: raise ValueError('Oversized source entry')
                line += 1; entry = json.loads(raw)
                for row in records(entry, line, counts, grammar['terms']):
                    fields = ','.join(row); marks = ','.join('?' for _ in row)
                    cursor = db.execute(f'INSERT INTO examples({fields}) VALUES ({marks})', tuple(row.values()))
                    db.execute('INSERT INTO context_search(docid,search_text) VALUES (?,?)', (cursor.lastrowid, row['search_text']))
                    counts['records_' + row['source_language'] + '-' + row['target_language']] += 1
                    if row['reading']: counts['records_with_reading_' + row['target_language']] += 1
                if line % 10000 == 0:
                    db.commit()
                    if path.stat().st_size > args.max_bytes: raise ValueError('Index exceeds declared bound')
                if line % 250000 == 0:
                    print(json.dumps({'source_entries': line, 'bytes': path.stat().st_size, 'seconds': round(time.monotonic()-start, 2)}), flush=True)
        receipt = {'schema': 'vipi-context-example-research-2', 'runtime_integration': False, 'linguistic_acceptance': False,
                   'source_selection_sha256': pinned['selection_sha256'], 'upstream_sha256': pinned['source_sha256'],
                   'compiler_sha256': digest_file(Path(__file__)),
                   'compiler_dependencies': {name: digest_file(Path(__file__).with_name(name)) for name in ('build_wiktextract.py','context_hints.py')},
                   'grammar_guard_sha256': digest_file(args.grammar_guard),
                   'grammar_policy': 'native-closed-class-phrases-2',
                   'offsets': 'Unicode code points; source and target contexts independently bounded',
                   'reading_policy': 'explicit-example-roman-span-only-1', 'source_entries': line, 'complete_source_scan': True,
                   'counts': dict(counts), 'fts': 'FTS4 unicode61 with CJK retrieval bigrams',
                   'records': db.execute('SELECT count(*) FROM examples').fetchone()[0],
                   'directions': db.execute('SELECT count(*) FROM (SELECT DISTINCT source_language,target_language FROM examples)').fetchone()[0],
                   'reading_records': db.execute("SELECT count(*) FROM examples WHERE reading<>''").fetchone()[0],
                   'source': pinned['source_url'], 'license': pinned['license'],
                   'limitations': ['Only explicit single-span usage examples; no inferred alignment.',
                                   'Direct English pairs only; no inferred non-English pivots.',
                                   'Only explicit readable romanization spans are retained; missing readings remain empty.',
                                   'Readings, sense selection and native execution not yet qualified.',
                                   'Search relevance is not permission to substitute.']}
        db.executemany('INSERT INTO metadata VALUES (?,?)', [(key, json.dumps(value, ensure_ascii=False)) for key, value in receipt.items()])
        db.execute("INSERT INTO context_search(context_search) VALUES ('integrity-check')")
        db.commit()
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    finally: db.close()
    receipt.update(bytes=path.stat().st_size, sha256=digest_file(path), seconds=time.monotonic()-start)
    if receipt['bytes'] > args.max_bytes: raise ValueError('Index exceeds declared bound')
    (args.output / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(receipt, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--grammar-guard', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--max-bytes', type=int, default=268435456)
    main(parser.parse_args())
