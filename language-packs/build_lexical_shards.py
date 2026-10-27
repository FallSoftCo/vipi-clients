#!/usr/bin/env python3
"""Compile indexed, sense-preserving public dictionary shards for native lookup.

One shard per language, shared sense identities, no pair Cartesian products.
Published dictionary evidence is deliberately distinct from authored assessment.
"""
import argparse
from collections import Counter, defaultdict
import json
import hashlib
from pathlib import Path
import sqlite3
import time
import unicodedata

from build_wiktextract import canonical, digest_file, EXCLUDED, PARTS, NON_ROMAN
from context_hints import lookup_key, has_scope, qualifier, GRAMMAR
from native_lemma_links import NativeLinks

POLICY = 'native-linked-analysis-concordance-2'
SCHEMA = '''
PRAGMA application_id=1447645257;
PRAGMA user_version=10;
PRAGMA temp_store=FILE;
PRAGMA cache_size=-16384;
CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE lexemes(id INTEGER PRIMARY KEY,headword TEXT NOT NULL,normalized TEXT NOT NULL,
 pos TEXT NOT NULL,source_safe INTEGER NOT NULL,target_safe INTEGER NOT NULL,
 senses INTEGER NOT NULL,source_url TEXT NOT NULL);
CREATE TABLE senses(id TEXT PRIMARY KEY,label TEXT NOT NULL,pos TEXT NOT NULL,
 explicit INTEGER NOT NULL,source_url TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE terms(lexeme INTEGER NOT NULL REFERENCES lexemes(id),sense TEXT NOT NULL REFERENCES senses(id),
 reading TEXT NOT NULL,eligible INTEGER NOT NULL,qualifiers TEXT NOT NULL,
 PRIMARY KEY(lexeme,sense,reading,qualifiers)) WITHOUT ROWID;
CREATE TABLE surfaces(normalized TEXT NOT NULL,lexeme INTEGER NOT NULL REFERENCES lexemes(id),
 surface TEXT NOT NULL,start INTEGER NOT NULL,end INTEGER NOT NULL,number INTEGER NOT NULL,
 mode INTEGER NOT NULL,features TEXT NOT NULL,
 PRIMARY KEY(normalized,lexeme,surface,start,end,number,mode,features)) WITHOUT ROWID;
CREATE TABLE guards(normalized TEXT PRIMARY KEY,blocked INTEGER NOT NULL,
 target_blocked INTEGER NOT NULL,protect_inner INTEGER NOT NULL,reason TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE lemma_links(source_line INTEGER PRIMARY KEY,canonical_line INTEGER NOT NULL,
 references_json TEXT NOT NULL,features TEXT NOT NULL,kind TEXT NOT NULL);
'''

def normalized(word, language):
    return lookup_key(word, language)

def letters(word):
    return bool(word) and all(unicodedata.category(c)[0] in ('L', 'M') for c in word)

def utf16(word):
    return len(word.encode('utf-16-le')) // 2

def native_senses(rows):
    """Count distinct modern leaf glosses, retaining all etymologies/entries."""
    meanings=set(); blocked=False
    for glosses,tags,form_of,alt_of in rows:
        tags=set(json.loads(tags))
        if tags & EXCLUDED:continue
        if json.loads(form_of) or json.loads(alt_of) or tags & {'form-of','alt-of'}:
            blocked=True;continue
        values=json.loads(glosses)
        if not values:blocked=True;continue
        meanings.add(values[-1])
    return len(meanings),blocked

def surface(head, form, pos, tags, language):
    """Only exact supplied forms. No stripping or generated conjugations."""
    tags=set(tags)
    if tags & (EXCLUDED | {'table-tags','romanization','transliteration','ipa','error'}):return None
    number=2 if pos=='noun' and 'plural' in tags and 'singular' not in tags else 0
    # Non-Roman readings belong to the supplied headword, never an invented
    # reading of its inflection. Whole single-word heads are still supported.
    if form==head:
        return (0,utf16(form),number,1) if letters(head) else (0,0,number,0)
    if language in NON_ROMAN or not letters(form):return (0,0,number,0)
    if pos=='noun' and 'plural' in tags and 'singular' not in tags:
        return 0,utf16(form),2,2
    if pos=='verb' and letters(head) and form.count(head)==1 and tags & {
        'indicative','present','past','future','conditional','imperative','subjunctive',
        'infinitive','participle','negative','positive','first-person','second-person','third-person'}:
        start=form.index(head)
        # A literal lexical root inside a fully attested carrier keeps all
        # source person/tense/negation affixes outside the displayed focus.
        return utf16(form[:start]),utf16(form[:start+len(head)]),0,3
    return 0,0,number,0

def compile_language(inventory, output, language, receipt, redirect_path, redirect_receipt, gloss_path, gloss_receipt, release_id):
    target=output/(language+'.sqlite'); counts=Counter();started=time.monotonic()
    source=sqlite3.connect(inventory.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
    source.execute('PRAGMA temp_store=FILE');source.execute('PRAGMA cache_size=-16384')
    redirects=defaultdict(list)
    with sqlite3.connect(redirect_path.resolve().as_uri()+'?mode=ro&immutable=1',uri=True) as redirect_db:
        for identifier,word in redirect_db.execute('SELECT source_line,target FROM redirects WHERE language=?',(language,)):
            redirects[identifier].append(word)
    links=NativeLinks(source,language,redirects)
    # Keep all supplied bilingual links, preserving English entry identities.
    linked_terms=defaultdict(list)
    for form,sid,reading,q,label,spos,explicit,surl,english,english_line in source.execute('''SELECT t.form,t.sense_id,t.display_reading,t.qualifiers,
        s.label,s.part_of_speech,s.explicit,s.source_url,s.source_word,s.source_line
        FROM terms t JOIN senses s ON s.id=t.sense_id WHERE t.language=?''',(language,)):
        if language=='en':identifiers=[english_line]
        else:
            candidates=links.candidates(form)
            roots={links.resolve(i) for i in candidates}
            matching={i for i in roots if links.entry(i)[3]==spos}
            # Cross-POS translations are allowed only with an explicit short
            # gloss counterpart, not merely a coincidentally shared spelling.
            identifiers=matching or {i for i in roots if english.lower() in links.simple_glosses(i)}
        for identifier in identifiers:
            root=links.resolve(identifier)
            glosses=links.simple_glosses(root) if language!='en' else set()
            contradiction=bool(glosses and english.lower() not in glosses)
            linked_terms[root].append((sid,reading,q,label,spos,explicit,surl,contradiction))
            if contradiction:counts['contradicted_links']+=1
    # Native definitions supply direct English relations absent from English
    # translation tables. A separate sense ID and explicit=0 prohibit using
    # these bare glosses as unreviewed pivots between two foreign languages.
    with sqlite3.connect(gloss_path.resolve().as_uri()+'?mode=ro&immutable=1',uri=True) as gloss_db:
        rows=gloss_db.execute('SELECT language,native_line,english_line,headword,english_word,gloss,reading,source_url FROM links'+
            ('' if language=='en' else ' WHERE language=?'),() if language=='en' else (language,))
        for foreign,native_id,english_id,head,english_word,gloss,reading,url in rows:
            identifier=english_id if language=='en' else native_id
            pos=links.entry(identifier)[3]
            sid=f'native-gloss:{foreign}:{native_id}'
            linked_terms[identifier].append((sid,'' if language=='en' else reading,'{}',gloss,pos,0,url,False))
            counts['direct_native_gloss_links']+=1
    mapped=set(linked_terms)
    with sqlite3.connect(target) as db:
        db.executescript(SCHEMA)
        inserted=set()
        def add_lexeme(identifier):
            if identifier in inserted:return
            _,head,key,pos,raw_tags,url=links.entry(identifier)
            n,nonlemma=native_senses(links.senses(identifier))
            word=source.execute('SELECT grammatical,proper FROM native_words WHERE language=? AND normalized=?',(language,key)).fetchone()
            lexical=not nonlemma and pos in PARTS and not set(json.loads(raw_tags))&EXCLUDED and n>0
            # Proper-name and grammatical homographs remain negative source
            # evidence. They do not invalidate another entry's lexical target.
            source_safe=int(lexical and n==1 and not (word and any(word)))
            db.execute('INSERT INTO lexemes VALUES (?,?,?,?,?,?,?,?)',(identifier,head,key,pos,source_safe,int(lexical),n,url))
            inserted.add(identifier)
        def add_surface(identifier,form,tags):
            _,head,key,pos,_,_=links.entry(identifier)
            rule=surface(head,form,pos,tags,language)
            # A supplied alternative script represents the same lexical unit;
            # its reading must still be present and unique at native lookup.
            if rule and rule[3]==0 and set(tags)&{'canonical','alternative'} and letters(form):
                rule=(0,utf16(form),0,1)
            if not rule or len(form)>128:return
            start,end,number,mode=rule
            db.execute('INSERT OR IGNORE INTO surfaces VALUES (?,?,?,?,?,?,?,?)',
                (normalized(form,language),identifier,form,start,end,number,mode,canonical(tags)))
        for index,identifier in enumerate(sorted(mapped)):
            add_lexeme(identifier)
            rows=linked_terms[identifier]
            scoped={sid for sid,reading,q,*rest in rows if has_scope(q)}
            for sid,reading,q,label,spos,explicit,surl,contradiction in rows:
                eligible=int(not contradiction and qualifier(q)=='' and sid not in scoped)
                db.execute('INSERT OR IGNORE INTO senses VALUES (?,?,?,?,?)',(sid,label,spos,explicit,surl))
                db.execute('INSERT OR IGNORE INTO terms VALUES (?,?,?,?,?)',(identifier,sid,reading,eligible,q))
            add_surface(identifier,links.entry(identifier)[1],[])
            for form,tags in source.execute('SELECT form,tags FROM native_forms WHERE source_line=?',(identifier,)):
                add_surface(identifier,form,json.loads(tags))
            if index%10000==0:db.commit()
        # Every independent native headword competing with a retained surface
        # is resolved. Explicit inflections collapse; true homographs remain.
        source.execute('CREATE TEMP TABLE wanted(normalized TEXT PRIMARY KEY) WITHOUT ROWID')
        source.executemany('INSERT INTO wanted VALUES (?)',db.execute('SELECT DISTINCT normalized FROM surfaces'))
        competitors=source.execute('''SELECT e.source_line FROM wanted w JOIN native_entries e
            ON e.normalized=w.normalized WHERE e.language=? ORDER BY e.source_line''',(language,))
        for (identifier,) in competitors:
            root=links.resolve(identifier);add_lexeme(root)
            if root==identifier:tags=[]
            else:tags=links.evidence[identifier][2]
            # Source headword remains the exact attested carrier. Resolve the
            # root before calculating its focus so aliases do not create a
            # false whole-word analysis beside the canonical carrier.
            add_surface(root,links.entry(identifier)[1],tags)
        known={row[0] for row in db.execute('SELECT DISTINCT normalized FROM lexemes')}
        for key,lexical,grammar,proper in source.execute('SELECT normalized,lexical,grammatical,proper FROM native_words WHERE language=?',(language,)):
            blocked=bool(grammar or proper or (lexical and key not in known and
                not source.execute('SELECT 1 FROM wanted WHERE normalized=?',(key,)).fetchone()))
            reason='grammar' if grammar else 'name' if proper else 'unresolved-native-entry' if blocked else 'native-word-boundary'
            # Target person/tense/negation words remain untouched, regardless
            # of a secondary lexical dictionary entry.
            target_blocked=int(key in GRAMMAR.get(language,set()))
            db.execute('INSERT INTO guards VALUES (?,?,?,?,?)',(key,int(blocked),target_blocked,1,reason))
        for original,(root,refs,features,kind) in sorted(links.evidence.items()):
            if root in inserted:db.execute('INSERT INTO lemma_links VALUES (?,?,?,?,?)',(original,root,canonical(refs),canonical(features),kind))
        metadata=dict(schema='vipi-lexical-shard-2',policy=POLICY,language=language,
            normalization='unicode-nfc-lower-arabic-harakat-v1',
            source_inventory_sha256=receipt['sha256'],source_sha256=receipt['upstream_sha256'],
            redirects_sha256=redirect_receipt['sha256'],native_gloss_links_sha256=gloss_receipt['sha256'],release_id=release_id,
            compiler_sha256=digest_file(Path(__file__)),linker_sha256=digest_file(Path(__file__).with_name('native_lemma_links.py')),
            quality='published-dictionary-concordance',individually_reviewed=False,license='CC-BY-SA-4.0')
        db.executemany('INSERT INTO metadata VALUES (?,?)',[(k,canonical(v)) for k,v in metadata.items()])
        db.commit()
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or db.execute('PRAGMA foreign_key_check').fetchone():raise ValueError('Invalid shard')
        for name in ('lexemes','senses','terms','surfaces','guards','lemma_links'):counts[name]=db.execute('SELECT count(*) FROM '+name).fetchone()[0]
        counts['unique_lexical_heads']=db.execute('SELECT count(DISTINCT normalized) FROM lexemes WHERE id IN (SELECT lexeme FROM terms WHERE eligible=1)').fetchone()[0]
        counts['source_single_sense_heads']=db.execute('SELECT count(DISTINCT normalized) FROM lexemes WHERE source_safe=1 AND id IN (SELECT lexeme FROM terms WHERE eligible=1)').fetchone()[0]
        counts['indexed_written_forms']=db.execute('SELECT count(DISTINCT normalized) FROM surfaces').fetchone()[0]
        counts['supplied_carriers']=db.execute('SELECT count(DISTINCT normalized) FROM surfaces WHERE mode=3').fetchone()[0]
    links.close();source.close()
    result=dict(language=language,sha256=digest_file(target),bytes=target.stat().st_size,counts=dict(counts),seconds=round(time.monotonic()-started,2))
    print(canonical(result),flush=True);return result

def build(inventory,output,languages,redirects,gloss_links):
    receipt=json.loads((inventory.parent/'receipt.json').read_text())
    if not receipt['complete_source_scan'] or receipt['sha256']!=digest_file(inventory):raise ValueError('Complete pinned inventory required')
    if len(set(languages))!=len(languages) or any(lang not in receipt['languages'] for lang in languages):raise ValueError('Unknown/repeated language')
    redirect_receipt=json.loads((redirects.parent/'receipt.json').read_text())
    if redirect_receipt['upstream_sha256']!=receipt['upstream_sha256'] or redirect_receipt['sha256']!=digest_file(redirects):raise ValueError('Pinned redirect supplement required')
    gloss_receipt=json.loads((gloss_links.parent/'receipt.json').read_text())
    if not gloss_receipt['complete'] or gloss_receipt['source_inventory_sha256']!=receipt['sha256'] or gloss_receipt['sha256']!=digest_file(gloss_links):raise ValueError('Pinned direct-gloss supplement required')
    release_id=hashlib.sha256(canonical(dict(inventory=receipt['sha256'],redirects=redirect_receipt['sha256'],glosses=gloss_receipt['sha256'],
        compiler=digest_file(Path(__file__)),linker=digest_file(Path(__file__).with_name('native_lemma_links.py')))).encode()).hexdigest()
    output.mkdir(parents=True,exist_ok=False)
    shards=[compile_language(inventory,output,language,receipt,redirects,redirect_receipt,gloss_links,gloss_receipt,release_id) for language in languages]
    summary=dict(schema='vipi-lexical-shards-1',policy=POLICY,release_id=release_id,inventory_sha256=receipt['sha256'],
        compiler_sha256=digest_file(Path(__file__)),shards=shards,
        total_bytes=sum(s['bytes'] for s in shards),runtime_qualified=False,release_ready=False,
        limits=['Published dictionary evidence, not individual linguistic review.',
            'Single modern source analysis is a conservative display prerequisite, not proof of perfect meaning.',
            'Indexed forms and language-pair combinations are not distinct vocabulary concepts.',
            'No new transliteration, conjugation or full translation is generated by this compiler.'])
    (output/'catalog.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    (output/'ATTRIBUTION.txt').write_text((inventory.parent/'ATTRIBUTION.txt').read_text()+
        '\nChanges: per-language indexed lexemes, all supplied analyses and guards, shared source sense IDs.\n'+
        'Native lexical evidence remains separately attributed through lexemes.source_url and senses.source_url.\n'+
        'Compiler: language-packs/build_lexical_shards.py. Published dictionary evidence is not author assessment.\n')
    print(canonical(summary),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inventory',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--language',action='append');p.add_argument('--redirects',type=Path,required=True);p.add_argument('--gloss-links',type=Path,required=True)
    a=p.parse_args();build(a.inventory,a.output,a.language or ['en','es','fr','de','it','pt','ar','zh','ja','ko','sw'],a.redirects,a.gloss_links)
