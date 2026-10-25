#!/usr/bin/env python3
"""Compile provenance-preserving vocabulary candidates, not accepted translations.

English Wiktionary translation groups are the pivot. A shared, explicit sense
label may link non-English terms; unlabeled groups never create those links.
The resulting schema is deliberately not accepted by the v1 native installer.
Run only on the development host under storage-build, using existing source data.
"""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import time
import unicodedata
from urllib.parse import quote

LANGUAGES = ('en', 'es', 'fr', 'de', 'it', 'pt', 'ar', 'zh', 'ja', 'ko')
NON_ROMAN = {'ar', 'zh', 'ja', 'ko'}
PARTS = {'noun', 'verb', 'adj', 'adv', 'intj'}
EXCLUDED = {'archaic', 'obsolete', 'dated', 'historical', 'rare', 'nonstandard', 'misspelling', 'error', 'uncommon'}
DIALECTS = {'Cantonese', 'Hokkien', 'Hakka', 'Wu', 'Min-Nan', 'Min-Dong', 'Dungan', 'Gan', 'Jin', 'Xiang', 'Teochew', 'Classical-Chinese', 'Literary-Chinese'}
MAX_LINE = 8 * 1024 * 1024
SCHEMA = '''
PRAGMA application_id=1447645257;
PRAGMA user_version=4;
PRAGMA journal_mode=DELETE;
PRAGMA temp_store=FILE;
PRAGMA cache_size=-16384;
CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE senses(id TEXT PRIMARY KEY, label TEXT NOT NULL, part_of_speech TEXT NOT NULL,
 source_word TEXT NOT NULL, source_line INTEGER NOT NULL, source_url TEXT NOT NULL,
 explicit INTEGER NOT NULL CHECK(explicit IN (0,1))) WITHOUT ROWID;
CREATE TABLE terms(sense_id TEXT NOT NULL REFERENCES senses(id), language TEXT NOT NULL,
 form TEXT NOT NULL, normalized TEXT NOT NULL, roman TEXT NOT NULL, display_reading TEXT NOT NULL,
 tags TEXT NOT NULL, origin TEXT NOT NULL, qualifiers TEXT NOT NULL,
 PRIMARY KEY(sense_id,language,form,roman,tags,qualifiers)) WITHOUT ROWID;
CREATE INDEX terms_lookup ON terms(language,normalized,sense_id);
'''


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024): digest.update(chunk)
    return digest.hexdigest()


def clean(value):
    return unicodedata.normalize('NFC', ' '.join(value.split())) if isinstance(value, str) else ''


def form_ok(value):
    return (0 < len(value) <= 128 and len(value.split()) <= 5 and any(c.isalpha() for c in value)
            and all(unicodedata.category(c)[0] in ('L', 'M') or c in " '-’" for c in value))


def readable_roman(value):
    # Preserve the original separately. These are conventional romanization
    # apostrophes, not synthesized pronunciation or generic script conversion.
    value = clean(value).translate(str.maketrans({'ʕ': "'", 'ʔ': "'", 'ʿ': "'", 'ʾ': "'"}))
    if not value or len(value) > 128 or not any(c.isalpha() for c in value): return ''
    for char in value:
        if char in " '-’." or unicodedata.category(char).startswith('M'): continue
        if not char.isalpha() or 'LATIN' not in unicodedata.name(char, ''): return ''
        # IPA extensions do not become readable merely because Unicode calls
        # their letters LATIN. Retain them as source evidence, abstain in UI.
        if 0x0250 <= ord(char) <= 0x02FF or 0x1D00 <= ord(char) <= 0x1DBF: return ''
    return value


def translations(entry):
    for index, item in enumerate(entry.get('translations', [])):
        if isinstance(item, dict):
            label = clean(item.get('sense', ''))
            yield ('label:' + label if label else 'unlabeled:' + str(index)), label, bool(label), item
    for index, sense in enumerate(entry.get('senses', [])):
        if not isinstance(sense, dict) or set(sense.get('tags', [])) & EXCLUDED: continue
        label = ' / '.join(clean(x) for x in sense.get('glosses', []) if isinstance(x, str))[:2048]
        for subindex, item in enumerate(sense.get('translations', [])):
            if isinstance(item, dict):
                yield ('sense:' + str(index) if label else f'unlabeled-sense:{index}:{subindex}'), label, bool(label), item


def add_entry(db, entry, line, counts):
    if entry.get('lang_code') != 'en' or entry.get('pos') not in PARTS: return
    source = clean(entry.get('word', ''))
    if not form_ok(source): counts['invalid_source'] += 1; return
    if set(entry.get('tags', [])) & EXCLUDED: counts['excluded_source'] += 1; return
    source_senses = entry.get('senses', [])
    if source_senses and all(set(s.get('tags', [])) & (EXCLUDED | {'form-of', 'alt-of'}) for s in source_senses):
        counts['nonlemma_source'] += 1; return
    # Sense identifiers include the original line, so homographs/etymologies
    # cannot accidentally merge on the spelling of their English headword.
    for group, label, explicit, item in translations(entry):
        code = item.get('code', item.get('lang_code'))
        language = 'zh' if code == 'cmn' else code
        if language not in LANGUAGES or language == 'en': continue
        tags = set(x for x in item.get('tags', []) if isinstance(x, str))
        if tags & EXCLUDED: counts['excluded_translation'] += 1; continue
        if language == 'zh' and tags & DIALECTS: counts['excluded_dialect'] += 1; continue
        if language == 'ar' and any(x.endswith('-Arabic') and x != 'Modern-Standard-Arabic' for x in tags):
            counts['excluded_dialect'] += 1; continue
        written = clean(item.get('word', ''))
        # Chinese upstream commonly supplies both Han variants as a slash
        # pair. Split written variants only; never guess which of two readings
        # belongs to a word in any language.
        forms = [clean(x) for x in written.split('/')] if language == 'zh' else [written]
        if not 1 <= len(forms) <= 2 or not all(form_ok(x) for x in forms): counts['invalid_target'] += 1; continue
        roman = clean(item.get('roman', ''))[:512]
        qualifiers = {key: clean(item[key])[:2048] for key in ('english', 'translation', 'note')
                      if isinstance(item.get(key), str) and clean(item[key])}
        raw_tags = sorted(set(clean(value)[:256] for value in item.get('raw_tags', []) if isinstance(value, str) and clean(value)))
        if raw_tags: qualifiers['raw_tags'] = raw_tags
        reading = readable_roman(roman) if language in NON_ROMAN else ''
        if language in NON_ROMAN and not reading: counts['missing_readable_roman'] += 1
        identifier = hashlib.sha256(canonical([line, source, entry['pos'], group]).encode()).hexdigest()
        db.execute('INSERT OR IGNORE INTO senses VALUES (?,?,?,?,?,?,?)', (identifier, label[:2048], entry['pos'], source, line, 'https://en.wiktionary.org/wiki/' + quote(source, safe='') + '#English', int(explicit)))
        db.execute('INSERT OR IGNORE INTO terms VALUES (?,?,?,?,?,?,?,?,?)', (identifier, 'en', source, source.lower(), '', '', '[]', 'headword', '{}'))
        for form in sorted(set(forms)):
            db.execute('INSERT OR IGNORE INTO terms VALUES (?,?,?,?,?,?,?,?,?)', (identifier, language, form, form.lower(), roman, reading, canonical(sorted(tags)), 'explicit_translation', canonical(qualifiers)))
            counts['term_candidates'] += 1
        counts['translations_retained'] += 1


def coverage(db):
    # No reverse or pivot relationship is asserted to be an accepted lexical
    # replacement. The classification remains explicit in this receipt.
    summary = []
    for source in LANGUAGES:
        for target in LANGUAGES:
            if source == target: continue
            extra = ' AND s.explicit=1' if source != 'en' and target != 'en' else ''
            sql = '''SELECT count(*), count(DISTINCT source), count(DISTINCT CASE WHEN readable THEN source END) FROM (
                SELECT a.normalized AS source,b.form AS target,
                    MAX(CASE WHEN ? NOT IN ('ar','zh','ja','ko') OR b.display_reading<>'' THEN 1 ELSE 0 END) AS readable
                FROM terms a JOIN terms b ON a.sense_id=b.sense_id JOIN senses s ON s.id=a.sense_id
                WHERE a.language=? AND b.language=?''' + extra + ' GROUP BY a.normalized,b.form)'
            mappings, headwords, readable = db.execute(sql, (target, source, target)).fetchone()
            summary.append({'source': source, 'target': target, 'candidate_pairs': mappings, 'source_headwords': headwords,
                'headwords_with_readable_target': readable, 'evidence': 'direct' if source == 'en' else 'reversed_direct' if target == 'en' else 'shared_explicit_english_sense',
                'quality': 'unqualified'})
    return summary


def compile_catalog(source, source_metadata, extraction, output, max_entries=0, max_bytes=1_073_741_824):
    metadata = json.loads(source_metadata.read_text()); selection = json.loads(extraction.read_text())
    pinned = json.loads((Path(__file__).parent/'sources'/'wiktextract-20261021.json').read_text())
    if metadata['sha256'] != pinned['source_sha256'] or metadata['bytes'] != pinned['source_bytes'] or source.stat().st_size != pinned['selection_bytes']:
        raise ValueError('Source does not match repository provenance pin')
    compiler_hash = digest_file(Path(__file__))
    if selection['source_sha256'] != metadata['sha256'] or source.stat().st_size != selection['compressed_bytes']:
        raise ValueError('Selected source provenance/size mismatch')
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic(); counts = Counter(); lines = 0
    source_hash = digest_file(source)
    if source_hash != pinned['selection_sha256']: raise ValueError('Selected source checksum mismatch')
    path = output / 'candidates.sqlite'
    db = sqlite3.connect(path); db.executescript(SCHEMA)
    completed = False
    try:
        with gzip.open(source, 'rb') as stream:
            while raw := stream.readline(MAX_LINE + 1):
                if len(raw) > MAX_LINE: raise ValueError('Source record exceeds bounded line size')
                lines += 1
                entry = json.loads(raw)
                if not isinstance(entry, dict): raise ValueError('Invalid source record')
                add_entry(db, entry, lines, counts)
                if lines % 25000 == 0:
                    db.commit()
                    if path.stat().st_size > max_bytes: raise ValueError('Catalog exceeds declared storage bound')
                    print(canonical({'read': lines, 'bytes': path.stat().st_size, 'seconds': round(time.monotonic()-started, 2)}), flush=True)
                if max_entries and lines >= max_entries: break
            else: completed = True
        for key,value in {'schema':'vipi-sense-candidates-4','quality':'unqualified','compiler_sha256':compiler_hash,'selected_source_sha256':source_hash,
            'upstream_sha256':metadata['sha256'],'languages':LANGUAGES,'license':'CC-BY-SA-4.0','source_version':metadata['extraction'],
            'normalization':'unicode-nfc-lower','selection_complete':completed}.items():
            db.execute('INSERT INTO metadata VALUES (?,?)', (key,canonical(value)))
        db.commit()
        if path.stat().st_size > max_bytes: raise ValueError('Catalog exceeds declared storage bound')
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok': raise ValueError('Catalog integrity failed')
        if db.execute('PRAGMA foreign_key_check').fetchone() is not None: raise ValueError('Catalog references failed')
        summary = coverage(db)
        senses, = db.execute('SELECT count(*) FROM senses').fetchone()
        terms, = db.execute('SELECT count(*) FROM terms').fetchone()
    finally: db.close()
    receipt = {'schema':4,'compiler_sha256':compiler_hash,'quality':'unqualified','complete_source_scan':completed,'source_entries_read':lines,'source':metadata,
        'selection_sha256':source_hash,'counts':dict(counts),'senses':senses,'terms':terms,'bytes':path.stat().st_size,
        'sha256':digest_file(path),'seconds':round(time.monotonic()-started,2),'pairs':summary,
        'limits':['Candidate mappings are not approved replacements.','Shared English sense is a derivation, not independent bilingual validation.',
            'Readings retain upstream evidence; missing, conflicting or contextual readings still require abstention.',
            'Term qualifiers, notes and raw tags remain available; shared sense labels alone do not prove equivalence.',
            'No quotations, audio, IPA fields or example sentences are included.','Schema 4 research catalogs are not native installable packs.']}
    (output/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    (output/'ATTRIBUTION.txt').write_text('Wiktionary contributors; extracted by Tatu Ylonen and wiktextract via Kaikki.org.\nData: CC BY-SA 4.0, https://creativecommons.org/licenses/by-sa/4.0/\nSource: '+metadata['url']+'\nOriginal entry and contributor history: source_url in senses; append ?action=history before #English.\nChanges: English translation-group selection, dialect/legacy filtering, Unicode normalization, conservative readable-romanization conversion, SQLite conversion.\nCompiler: language-packs/build_wiktextract.py in Vipi corresponding source.\nCandidate data has not passed contextual language acceptance.\n')
    print(canonical({k:receipt[k] for k in ('complete_source_scan','source_entries_read','senses','terms','bytes','sha256','seconds')}),flush=True)
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('source','source-metadata','extraction','output'): parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--max-entries',type=int,default=0)
    parser.add_argument('--max-bytes',type=int,default=1_073_741_824)
    args=parser.parse_args()
    if args.max_entries < 0 or args.max_bytes < 1: parser.error('Bounds must be nonnegative/positive')
    compile_catalog(args.source,args.source_metadata,args.extraction,args.output,args.max_entries,args.max_bytes)
