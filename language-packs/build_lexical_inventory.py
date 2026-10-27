#!/usr/bin/env python3
"""Build the full eleven-language lexical inventory from the pinned dictionary.

Sense links, native analyses and supplied inflections remain separate evidence.
This inventory is not a reviewed-frame export or an automatically approved pack.
All line identities refer to the complete upstream file, including Swahili.
"""
import argparse
from collections import Counter, defaultdict
import gzip
import json
from pathlib import Path
import sqlite3
import time
import unicodedata
from urllib.parse import quote

from build_wiktextract import (LANGUAGES, MAX_LINE, PARTS, SCHEMA, add_entry,
    canonical, clean, digest_file, form_ok)
from context_hints import lookup_key

LANGUAGES = (*LANGUAGES, 'sw')
CATALOG_SHA = '547122b54c3dfb1d90f581d3d6534695a8e934787bf856d1ec828f8eb676daba'
SWAHILI_SHA = '46395c3ed74c76ec55e2006c9ea665b4e2a11384877dd3fb264d8a32297cdbae'
NATIVE_SCHEMA = '''
CREATE TABLE native_words(language TEXT NOT NULL, normalized TEXT NOT NULL,
 lexical INTEGER NOT NULL, grammatical INTEGER NOT NULL, proper INTEGER NOT NULL,
 entries INTEGER NOT NULL, PRIMARY KEY(language,normalized)) WITHOUT ROWID;
CREATE TABLE native_entries(source_line INTEGER PRIMARY KEY, language TEXT NOT NULL,
 headword TEXT NOT NULL, normalized TEXT NOT NULL, part_of_speech TEXT NOT NULL,
 tags TEXT NOT NULL, source_url TEXT NOT NULL);
CREATE INDEX native_entry_lookup ON native_entries(language,normalized);
CREATE TABLE native_senses(source_line INTEGER NOT NULL REFERENCES native_entries(source_line),
 sense_index INTEGER NOT NULL, glosses TEXT NOT NULL, tags TEXT NOT NULL,
 form_of TEXT NOT NULL, alt_of TEXT NOT NULL,
 PRIMARY KEY(source_line,sense_index)) WITHOUT ROWID;
CREATE TABLE native_forms(source_line INTEGER NOT NULL REFERENCES native_entries(source_line),
 form TEXT NOT NULL, normalized TEXT NOT NULL, tags TEXT NOT NULL,
 PRIMARY KEY(source_line,form,tags)) WITHOUT ROWID;
CREATE INDEX native_forms_lookup ON native_forms(normalized,source_line);
'''

def strings(values):
    return sorted({clean(value) for value in values if isinstance(value,str) and clean(value)})

def links(values):
    return [dict(word=clean(value['word']), extra=clean(value.get('extra','')))
        for value in values if isinstance(value,dict) and isinstance(value.get('word'),str)]

def key(word, language):
    return lookup_key(word, language) if language!='sw' else unicodedata.normalize('NFC',word).lower()

def vocabulary_heads(catalog, swahili):
    heads=defaultdict(set)
    for path,expected in [(catalog,CATALOG_SHA),(swahili,SWAHILI_SHA)]:
        if digest_file(path)!=expected:raise ValueError('Changed vocabulary evidence: '+str(path))
        with sqlite3.connect(path.resolve().as_uri()+'?mode=ro&immutable=1',uri=True) as db:
            for language,word in db.execute('SELECT DISTINCT language,form FROM terms'):
                heads[language].add(key(word,language))
    return heads

def add_native(db, entry, line, heads, counts, all_native=False):
    language=entry.get('lang_code');language='zh' if language=='cmn' else language
    if language not in LANGUAGES:return
    head=clean(entry.get('word',''));pos=entry.get('pos','')
    if not form_ok(head):return
    normalized=key(head,language)
    lexical=pos in PARTS;proper=pos in {'name','proper-noun','proper_noun'}
    grammatical=pos in {'pron','det','prep','postp','conj','particle','article','aux'}
    sense_tags={tag for sense in entry.get('senses',[]) if isinstance(sense,dict)
        for tag in sense.get('tags',[]) if isinstance(tag,str)}
    grammatical |= bool(sense_tags & {'auxiliary','modal','pronoun','determiner','preposition','conjunction'})
    proper |= 'proper-noun' in sense_tags
    db.execute('''INSERT INTO native_words VALUES (?,?,?,?,?,1)
        ON CONFLICT(language,normalized) DO UPDATE SET
        lexical=max(lexical,excluded.lexical), grammatical=max(grammatical,excluded.grammatical),
        proper=max(proper,excluded.proper), entries=entries+1''',
        (language,normalized,int(lexical),int(grammatical),int(proper)))
    counts['native_word_entries']+=1
    # Retain full native analyses for mapped headwords and the complete Swahili
    # vocabulary. Other words still guard compounds/grammar/names above.
    if not all_native and normalized not in heads[language] and language!='sw':return
    tags=strings(entry.get('tags',[]))
    db.execute('INSERT INTO native_entries VALUES (?,?,?,?,?,?,?)',
        (line,language,head,normalized,pos,canonical(tags),
         'https://en.wiktionary.org/wiki/'+quote(head,safe='')+'#'+quote(entry.get('lang',language),safe='')))
    counts['native_entries']+=1
    for index,sense in enumerate(entry.get('senses',[])):
        if not isinstance(sense,dict):continue
        glosses=[value for value in sense.get('glosses',[]) if isinstance(value,str)]
        db.execute('INSERT INTO native_senses VALUES (?,?,?,?,?,?)',
            (line,index,canonical(glosses),canonical(strings(sense.get('tags',[]))),
             canonical(links(sense.get('form_of',[]))),canonical(links(sense.get('alt_of',[])))))
        counts['native_senses']+=1
    for form in entry.get('forms',[]):
        if not isinstance(form,dict):continue
        value=clean(form.get('form',''))
        if not form_ok(value):continue
        before=db.total_changes
        db.execute('INSERT OR IGNORE INTO native_forms VALUES (?,?,?,?)',
            (line,value,key(value,language),canonical(strings(form.get('tags',[])))))
        counts['native_forms']+=db.total_changes-before

def build(source,catalog,swahili,output,max_bytes,all_native=False):
    pin=json.loads(Path(__file__).with_name('sources').joinpath('wiktextract-20261021.json').read_text())
    if source.stat().st_size!=pin['source_bytes'] or digest_file(source)!=pin['source_sha256']:
        raise ValueError('Exact full upstream source required')
    heads=vocabulary_heads(catalog,swahili)
    output.mkdir(parents=True,exist_ok=False);path=output/'inventory.sqlite'
    started=time.monotonic();counts=Counter();lines=0
    def bound():
        used=sum(p.stat().st_size for p in output.iterdir() if p.is_file())
        if used>max_bytes:raise ValueError('Declared inventory storage bound exceeded')
        return used
    with sqlite3.connect(path) as db:
        db.executescript(SCHEMA+NATIVE_SCHEMA)
        with gzip.open(source,'rb') as stream:
            while raw:=stream.readline(MAX_LINE+1):
                if len(raw)>MAX_LINE:raise ValueError('Oversized upstream entry')
                lines+=1;entry=json.loads(raw)
                if not isinstance(entry,dict):raise ValueError('Invalid upstream entry')
                add_entry(db,entry,lines,counts,LANGUAGES)
                add_native(db,entry,lines,heads,counts,all_native)
                if lines%25000==0:
                    db.commit();used=bound()
                    if lines%250000==0:
                        print(canonical(dict(lines=lines,bytes=used,seconds=round(time.monotonic()-started,2),counts=dict(counts))),flush=True)
        metadata=dict(schema='vipi-lexical-inventory-2',languages=LANGUAGES,
            native_scope='all-native-entries' if all_native else 'mapped-headwords-and-all-swahili',
            upstream_sha256=pin['source_sha256'],source_version=pin['extraction'],license=pin['license'],
            quality='published-dictionary-evidence-not-individually-reviewed',
            compiler_sha256=digest_file(Path(__file__)),
            shared_compiler_sha256=digest_file(Path(__file__).with_name('build_wiktextract.py')),
            prior_catalog_sha256=CATALOG_SHA,swahili_evidence_sha256=SWAHILI_SHA,
            source_line_identity='full-upstream-file',normalization='unicode-nfc-lower-arabic-harakat-v1')
        db.executemany('INSERT INTO metadata VALUES (?,?)',[(k,canonical(v)) for k,v in metadata.items()])
        db.commit();bound()
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert db.execute('PRAGMA foreign_key_check').fetchone() is None
        terms=[dict(language=lang,records=n,unique_forms=unique,readable_forms=readable)
            for lang,n,unique,readable in db.execute('''SELECT language,count(*),count(DISTINCT normalized),
                count(DISTINCT CASE WHEN display_reading<>'' THEN normalized END) FROM terms GROUP BY language''')]
        native=[dict(language=lang,headwords=heads,recorded_forms=forms)
            for lang,heads,forms in db.execute('''SELECT e.language,count(DISTINCT e.normalized),count(f.form)
                FROM native_entries e LEFT JOIN native_forms f USING(source_line) GROUP BY e.language''')]
        senses=db.execute('SELECT count(*) FROM senses').fetchone()[0]
    receipt=dict(**metadata,complete_source_scan=True,source_entries=lines,counts=dict(counts),
        sense_groups=senses,terms=terms,native=native,bytes=path.stat().st_size,sha256=digest_file(path),
        seconds=round(time.monotonic()-started,2),runtime_promoted=False,release_ready=False,
        limits=['Dictionary evidence is not independent conversational accuracy.',
            'Native inflections retain exact supplied forms/features; no arbitrary stemming or inferred conjugation.',
            'Sense identifiers preserve separate entries and etymologies; shared pivots are not independent translations.',
            'No evaluation messages, quoted examples, audio or IPA fields are copied.'])
    (output/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    (output/'ATTRIBUTION.txt').write_text('Wiktionary contributors; extraction by Tatu Ylonen/wiktextract via Kaikki.org.\n'
        'CC BY-SA 4.0. https://creativecommons.org/licenses/by-sa/4.0/\n'
        'Source: '+pin['source_url']+'; exact SHA-256: '+pin['source_sha256']+'\n'
        'Entry URLs and full-source line identities are retained; contributor histories remain at those entries.\n'
        'Changes: eleven-language translation groups, native word guards, selected native analyses and supplied forms; SQLite indexing.\n'
        'Transformation source: language-packs/build_lexical_inventory.py and build_wiktextract.py.\n'
        'No claim of individual review or automatic runtime approval.\n')
    print(canonical(receipt),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['source','catalog','swahili','output']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--max-bytes',type=int,default=1_800_000_000)
    p.add_argument('--all-native',action='store_true',help='Retain complete native analyses, including linked aliases and inflected entries outside the bilingual headword list.')
    a=p.parse_args();build(a.source,a.catalog,a.swahili,a.output,a.max_bytes,a.all_native)
