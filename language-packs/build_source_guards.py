#!/usr/bin/env python3
"""Retain native Chinese lexemes and unresolved polysemy as negative evidence.

This index supplies no translations. English-pivot coverage must not decide
whether a compound or competing native meaning exists. Native ambiguity vetoes
generic substitutions; an explicitly reviewed message scope is a separate path.
"""
import argparse
import gzip
import json
from pathlib import Path
import sqlite3
import time
import unicodedata

from build_wiktextract import canonical, digest_file

POLICY = 'attested-native-han-lexeme-and-polysemy-veto-1'
SCHEMA = '''
PRAGMA application_id=1447645257;
PRAGMA user_version=1;
PRAGMA temp_store=FILE;
CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE attestations(source TEXT NOT NULL,claim TEXT NOT NULL,evidence TEXT NOT NULL,
 PRIMARY KEY(source,claim,evidence)) WITHOUT ROWID;
CREATE TABLE source_guards(source TEXT PRIMARY KEY,protect_inner INTEGER NOT NULL,
 ambiguous INTEGER NOT NULL,evidence TEXT NOT NULL) WITHOUT ROWID;
'''


def han_word(value):
    return (isinstance(value,str) and 1<=len(value)<=32 and
            all('CJK UNIFIED IDEOGRAPH' in unicodedata.name(c,'') or
                'CJK COMPATIBILITY IDEOGRAPH' in unicodedata.name(c,'') for c in value))


def collect(db,entry,line):
    if entry.get('lang_code')!='zh':return
    head=entry.get('word','')
    forms={head} if han_word(head) else set()
    # Only explicit script variants inherit claims. Inflections, romanization,
    # pronunciations and arbitrary synonyms cannot create a lexical boundary.
    for form in entry.get('forms',[]):
        tags=set(form.get('tags',[])) if isinstance(form,dict) else set()
        value=form.get('form','') if isinstance(form,dict) else ''
        if tags and tags<={'Simplified-Chinese','Traditional-Chinese'} and han_word(value):forms.add(value)
    for sense in entry.get('senses',[]):
        glosses=sense.get('glosses',[])
        if not glosses or not all(isinstance(x,str) for x in glosses):continue
        # No attempt to decide whether differently worded senses are equivalent.
        # Their distinction is uncertainty, not a newly approved mapping.
        claim=canonical({'pos':entry.get('pos'), 'glosses':glosses,
                         'tags':sorted(sense.get('tags',[]))})
        evidence=canonical({'selection_line':line,'headword':head,'part_of_speech':entry.get('pos')})
        db.executemany('INSERT OR IGNORE INTO attestations VALUES (?,?,?)',
                       [(word,claim,evidence) for word in sorted(forms)])


def finish(db):
    for word,count in db.execute('SELECT source,count(DISTINCT claim) FROM attestations GROUP BY source').fetchall():
        if len(word)==1 and count==1:continue
        evidence=[{'claim':json.loads(claim),'source':json.loads(source)} for claim,source in
                  db.execute('SELECT claim,evidence FROM attestations WHERE source=? ORDER BY claim,evidence',(word,))]
        db.execute('INSERT INTO source_guards VALUES (?,?,?,?)',
                   (word,int(len(word)>1),int(count>1),canonical(evidence)))


def build(source,output):
    pin=json.loads(Path(__file__).with_name('sources').joinpath('wiktextract-20261021.json').read_text())
    if source.stat().st_size!=pin['selection_bytes'] or digest_file(source)!=pin['selection_sha256']:
        raise ValueError('Pinned native dictionary selection required')
    output.mkdir(parents=True,exist_ok=False)
    started=time.monotonic();path=output/'source-guards.sqlite'
    with sqlite3.connect(path) as db:
        db.executescript(SCHEMA)
        with gzip.open(source,'rb') as stream:
            for line,raw in enumerate(stream,1):
                if len(raw)>8*1024*1024:raise ValueError('Oversized source entry')
                collect(db,json.loads(raw),line)
                if line%250_000==0:
                    db.commit()
                    if path.stat().st_size>268_435_456:raise ValueError('Guard index exceeded storage bound')
                    print(canonical({'lines':line,'seconds':time.monotonic()-started}),flush=True)
        finish(db)
        metadata={'schema':'vipi-native-source-guards-1','language':'zh','policy':POLICY,
                  'selection_sha256':pin['selection_sha256'],'upstream_sha256':pin['source_sha256'],
                  'compiler_sha256':digest_file(Path(__file__)),'license':'CC-BY-SA-4.0',
                  'attribution':'Wiktionary contributors; Tatu Ylonen/wiktextract via Kaikki.org.',
                  'quality':'negative_evidence_only'}
        db.executemany('INSERT INTO metadata VALUES (?,?)',metadata.items());db.commit()
        counts=dict(zip(('lexemes','protect_inner','ambiguous'),db.execute(
            'SELECT count(*),sum(protect_inner),sum(ambiguous) FROM source_guards').fetchone()))
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Integrity failure')
    receipt={**metadata,'sha256':digest_file(path),'bytes':path.stat().st_size,'counts':counts,
             'seconds':time.monotonic()-started,'release_ready':False,
             'limits':['Native dictionary senses can be redundant or incomplete.',
                       'This veto can reduce availability; it does not approve any translation.',
                       'Only Chinese Han headwords and explicit Han script variants are included.']}
    (output/'receipt.json').write_text(canonical(receipt)+'\n')
    print(canonical(receipt),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();build(args.source,args.output)
