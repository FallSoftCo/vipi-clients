#!/usr/bin/env python3
"""Index the full lexical vocabulary against directly linked development text.

This produces attributed context evidence, not automatically accepted mappings.
No reserved sentences, inferred translation links, invented readings or model
outputs are used. All meanings competing at a written form remain in lexicon.
"""
import argparse
from collections import Counter, defaultdict
from functools import lru_cache
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sqlite3
import sys
import time
import unicodedata
import ahocorasick
import icu
from conversation_corpus import sha_file, write_json
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'language-packs'))
from build_wiktextract import canonical
from context_hints import lookup_key


def readonly(path):
    db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
    db.execute('PRAGMA temp_store=FILE')
    db.execute('PRAGMA cache_size=-16384')
    return db



def select_changed_pair_endpoints(db, languages, changed):
    """Only development endpoints directly linked to a changed language.

    Restrict work, not evidence thresholds. Canonical input link identities and
    existing reserved-component exclusions remain intact. No transitive links.
    """
    assert changed and set(changed)<=set(languages)
    db.execute("CREATE TEMP TABLE changed_pair_endpoints(id INTEGER PRIMARY KEY)")
    marks=",".join("?" for _ in languages)
    changed_marks=",".join("?" for _ in changed)
    # Keep the indexed sentence lookups inside the link scan. With only
    # partition statistics SQLite can otherwise enumerate both sentence sets
    # before probing links (quadratic in the corpus size).
    query=f"""SELECT l.a,l.b FROM links l NOT INDEXED CROSS JOIN sentences a ON a.id=l.a
        CROSS JOIN sentences b ON b.id=l.b
        WHERE a.partition='development' AND b.partition='development'
        AND a.language<>b.language AND a.language IN ({marks}) AND b.language IN ({marks})
        AND (a.language IN ({changed_marks}) OR b.language IN ({changed_marks}))"""
    batch=[]
    for a,b in db.execute(query,[*languages,*languages,*changed,*changed]):
        batch.extend([(a,),(b,)])
        if len(batch)>=10000:
            db.executemany("INSERT OR IGNORE INTO changed_pair_endpoints VALUES (?)",batch);batch=[]
    db.executemany("INSERT OR IGNORE INTO changed_pair_endpoints VALUES (?)",batch)
    return db.execute("SELECT count(*) FROM changed_pair_endpoints").fetchone()[0]


def normalized_offsets(text, language):
    """Map each normalized code point to a complete original Unicode cluster.

    No native UTF-16 offset is derived from a normalized string's length.
    Cluster expansions/contractions preserve the exact original source span.
    """
    pieces = []; starts = []; ends = []; offset = 0; i = 0
    while i < len(text):
        j = i + 1
        while j < len(text) and unicodedata.combining(text[j]):
            j += 1
        cluster = text[i:j]; length = len(cluster.encode('utf-16-le')) // 2
        value = lookup_key(cluster, language)
        # lookup_key is a word normalizer; internal whitespace must survive.
        if cluster.isspace():
            value = cluster.lower()
        pieces.append(value); starts.extend([offset] * len(value))
        ends.extend([offset + length] * len(value)); offset += length; i = j
    return ''.join(pieces), starts, ends


def sentence_hits(text, language, automaton, forms):
    normalized, starts, ends = normalized_offsets(text, language)
    iterator = icu.BreakIterator.createWordInstance(icu.Locale(language))
    iterator.setText(icu.UnicodeString(text))
    boundaries = {0, *list(iterator)}
    result = set()
    for last, index in automaton.iter(normalized):
        word, analyses, form_id = forms[index]; first = last + 1 - len(word)
        # A match cannot consume half of an expanded Unicode cluster.
        if first and starts[first] == starts[first - 1]:
            continue
        if last + 1 < len(ends) and ends[last] == ends[last + 1]:
            continue
        start, end = starts[first], ends[last]
        if start not in boundaries or end not in boundaries:
            continue
        actual = text.encode('utf-16-le')[start*2:end*2].decode('utf-16-le')
        if lookup_key(actual, language) != word:
            continue
        result.add((form_id,start,end,actual))
    return sorted(result)


def load_lexicon(shard, language, sense_ids, output):
    db = readonly(shard); terms = defaultdict(list)
    for lexeme, sense, reading, explicit in db.execute('''SELECT t.lexeme,t.sense,t.reading,s.explicit
        FROM terms t JOIN senses s ON s.id=t.sense WHERE t.eligible=1 ORDER BY t.lexeme,t.sense,t.reading'''):
        terms[lexeme].append((sense_ids[sense], reading, explicit))
    by_word = defaultdict(dict)
    # Exact indexed carriers contribute only their lexical focus. Never assign
    # the full inflected word the meaning of its noun/verb stem.
    for word, lexeme, safe, mode, written, start, end in db.execute('''SELECT DISTINCT s.normalized,s.lexeme,l.source_safe,s.mode,s.surface,s.start,s.end
        FROM surfaces s JOIN lexemes l ON l.id=s.lexeme
        WHERE s.mode IN (1,2,3) AND l.target_safe=1 ORDER BY s.normalized,s.lexeme'''):
        if lexeme in terms:
            if lexeme not in by_word[word]:by_word[word][lexeme] = [lexeme, safe, terms[lexeme], []]
            by_word[word][lexeme][3].append([mode,written,start,end])
    # Retain competing native analyses, including ones without usable links.
    for word, lexeme, safe in db.execute('''SELECT DISTINCT s.normalized,s.lexeme,l.source_safe
        FROM surfaces s JOIN lexemes l ON l.id=s.lexeme ORDER BY s.normalized,s.lexeme'''):
        if word in by_word and lexeme not in by_word[word]:
            by_word[word][lexeme] = [lexeme, safe, [], []]
    first_id=output.execute('SELECT coalesce(max(id),0)+1 FROM lexicon').fetchone()[0]
    forms = [(word, list(values.values()), first_id+i) for i,(word,values) in enumerate(sorted(by_word.items()))]
    output.executemany('INSERT INTO lexicon VALUES (?,?,?,?)',
        ((identifier,language,word,canonical(analyses)) for word,analyses,identifier in forms))
    automaton = ahocorasick.Automaton(ahocorasick.STORE_INTS)
    for index, (word, _, _) in enumerate(forms):
        if word:
            automaton.add_word(word, index)
    automaton.make_automaton(); db.close()
    return automaton, forms


def unique_hits(payload, analyses):
    by_sense = defaultdict(set)
    for hit in json.loads(payload):
        form_id,start,end=hit[:3]
        for analysis in analyses(form_id):
            lexeme,safe,terms=analysis[:3]
            geometries={(start,end)} if len(analysis)==3 else set()
            for mode,written,a,b in analysis[3] if len(analysis)>3 else []:
                if mode in (1,2):geometries.add((start,end));continue
                actual=hit[3];encoded=actual.encode('utf-16-le')
                if mode!=3 or actual.lower()!=written.lower() or len(encoded)!=len(written.encode('utf-16-le')) or not 0<=a<b<=len(encoded)//2:continue
                try:encoded[2*a:2*b].decode('utf-16-le')
                except UnicodeDecodeError:continue
                geometries.add((start+a,start+b))
            for a,b in geometries:
                for sense,reading,explicit in terms:
                    by_sense[sense].add((a,b,lexeme,safe,reading,explicit))
    return {sense: next(iter(values)) for sense, values in by_sense.items() if len(values) == 1}


def build(args):
    started = time.monotonic(); args.output.mkdir(parents=True, exist_ok=False)
    catalog = json.loads((args.shards/'catalog.json').read_text())
    assert catalog['schema'] == 'vipi-lexical-shards-1'
    input_receipt=json.loads((args.corpus.parent/'receipt.json').read_text())
    assert sha_file(args.corpus)==input_receipt['sha256']
    corpus = readonly(args.corpus)
    source_receipt = json.loads(corpus.execute("SELECT value FROM metadata WHERE key='receipt'").fetchone()[0])
    is_pgv=input_receipt.get('schema')=='vipi-pgv-corpus-1'
    if is_pgv:
        assert source_receipt['schema']==input_receipt['schema']
        assert source_receipt['complete'] and source_receipt['direct_links_only'] and source_receipt['automatic_alignment']
        assert not args.supplement, 'PGV uses its own duplicate/exclusion components'
        sentence_license=source_receipt['license']
        attribution=('Sentence text: Global Voices contributors; automatically aligned by PGV, CC BY 4.0. '
            'Archive URLs and unit IDs in sentences.owner, source_attribution and source_link_evidence.\n'
            'Source: https://nlp.ilsp.gr/pgv/ . '+source_receipt['citation']+'\n')
    else:
        assert source_receipt.get('tags_schema') == 'tag_id,sentence_id,username,added_time'
        sentence_license='CC BY 2.0 FR: Tatoeba sentences'
        attribution=('Sentence text: Tatoeba contributors, CC BY 2.0 FR; owners in sentences.owner '
            'and links https://tatoeba.org/en/sentences/show/{id}.\n')
    sources=[('corpus',args.corpus,corpus)]
    language_sources={r[0]:corpus for r in corpus.execute('SELECT DISTINCT language FROM sentences')}
    supplemental_receipts=[]
    if args.supplement:
        for i,path in enumerate(args.supplement):
            receipt=json.loads((path.parent/'receipt.json').read_text())
            assert receipt['schema']=='vipi-swahili-development-supplement-1'
            assert receipt['parent_receipt_sha256']==sha_file(args.corpus.parent/'receipt.json')
            assert sha_file(path)==receipt['sha256']
            audit=json.loads((path.parent/'duplicate-audit.json').read_text())
            assert audit['complete_duplicate_neighbor_evidence']
            supplement=readonly(path);sources.append(('supplement'+str(i),path,supplement))
            for (language,) in supplement.execute('SELECT DISTINCT language FROM sentences'):
                if language not in language_sources:language_sources[language]=supplement
            supplemental_receipts.append(dict(receipt_sha256=sha_file(path.parent/'receipt.json'),corpus_sha256=receipt['sha256'],duplicate_audit_sha256=sha_file(path.parent/'duplicate-audit.json')))
    languages = args.language or sorted(language_sources)
    selected = [s for s in catalog['shards'] if s['language'] in languages]
    assert set(languages) == {s['language'] for s in selected}
    changed=getattr(args,'pair_language',None) or []
    assert set(changed)<=set(languages)
    endpoint_counts={}
    if changed:
        for name,_,input_db in sources:
            endpoint_counts[name]=select_changed_pair_endpoints(input_db,languages,changed)
        # Supplement links can refer to a main-corpus endpoint. Retain their
        # union in each reader; otherwise a language owned by the main input
        # could silently miss a new supplement-only direct neighbor.
        endpoint_ids={row[0] for _,_,input_db in sources
            for row in input_db.execute("SELECT id FROM changed_pair_endpoints")}
        for _,_,input_db in sources:
            input_db.executemany("INSERT OR IGNORE INTO changed_pair_endpoints VALUES (?)",
                ((identifier,) for identifier in endpoint_ids))
        endpoint_counts["union"]=len(endpoint_ids)
        print(canonical(dict(stage='changed_pair_endpoints',languages=changed,counts=endpoint_counts)),flush=True)
    context_path = args.output/'contexts.sqlite'; work = sqlite3.connect(context_path)
    work.executescript('''PRAGMA temp_store=FILE; PRAGMA cache_size=-32768;
        CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL) WITHOUT ROWID;
        CREATE TABLE senses(id INTEGER PRIMARY KEY,source_id TEXT UNIQUE NOT NULL,label TEXT NOT NULL,pos TEXT NOT NULL,url TEXT NOT NULL);
        CREATE TABLE lexicon(id INTEGER PRIMARY KEY,language TEXT NOT NULL,normalized TEXT NOT NULL,analyses TEXT NOT NULL,UNIQUE(language,normalized));
        CREATE TABLE sentences(id INTEGER PRIMARY KEY,language TEXT NOT NULL,text TEXT NOT NULL,owner TEXT NOT NULL,component INTEGER NOT NULL);
        CREATE TABLE focus(sentence INTEGER PRIMARY KEY,payload TEXT NOT NULL);
        CREATE TABLE alignments(a INTEGER NOT NULL,b INTEGER NOT NULL,sense INTEGER NOT NULL,
            a_start INTEGER NOT NULL,a_end INTEGER NOT NULL,b_start INTEGER NOT NULL,b_end INTEGER NOT NULL,
            a_lexeme INTEGER NOT NULL,b_lexeme INTEGER NOT NULL,a_single_sense INTEGER NOT NULL,b_single_sense INTEGER NOT NULL,
            a_reading TEXT NOT NULL,b_reading TEXT NOT NULL,PRIMARY KEY(a,b,sense)) WITHOUT ROWID;
        CREATE INDEX alignments_sense ON alignments(sense,a,b);
        CREATE VIRTUAL TABLE sentence_search USING fts5(language UNINDEXED,text,content='sentences',content_rowid='id',tokenize='unicode61 remove_diacritics 0');''')
    sense_ids = {}
    for shard in selected:
        file = args.shards/(shard['language']+'.sqlite')
        assert sha_file(file) == shard['sha256']
        with readonly(file) as db:
            for sid, label, pos, url in db.execute('SELECT id,label,pos,source_url FROM senses ORDER BY id'):
                if sid not in sense_ids:
                    identifier = len(sense_ids)+1; sense_ids[sid] = identifier
                    work.execute('INSERT INTO senses VALUES (?,?,?,?,?)', (identifier,sid,label,pos,url))
    work.commit()
    print(canonical(dict(stage='editorial_flags')),flush=True)
    flagged = {r[0] for _,_,input_db in sources for r in input_db.execute('''SELECT t.sentence FROM tags t NOT INDEXED JOIN tag_metadata m ON m.id=t.tag
        WHERE m.name LIKE '@%' OR lower(m.name) LIKE '%unnatural%' OR lower(m.name) LIKE '%incorrect%'
        OR lower(m.name) IN ('not natural','non natural','less than natural')''')}
    print(canonical(dict(stage='lexical_scan',flagged=len(flagged))),flush=True)
    counts = Counter(); per_language = {}; started_scan = time.monotonic()
    for language in languages:
        automaton, forms = load_lexicon(args.shards/(language+'.sqlite'), language, sense_ids, work)
        language_counts = Counter(); batch = []; focus_batch = []
        sql = "SELECT id,language,text,owner,component FROM sentences NOT INDEXED WHERE partition='development' AND language=? AND length(text) BETWEEN 2 AND 280 ORDER BY id"
        if changed:
            sql=sql.replace("sentences NOT INDEXED","sentences").replace(" ORDER BY id",
                " AND id IN (SELECT id FROM changed_pair_endpoints) ORDER BY id")
        if args.max_sentences_per_language:
            sql += ' LIMIT '+str(args.max_sentences_per_language)
        for row in language_sources[language].execute(sql,(language,)):
            language_counts['development_sentences_scanned'] += 1
            if row[0] in flagged:
                language_counts['editorially_flagged'] += 1; continue
            hits = sentence_hits(row[2],language,automaton,forms)
            if not hits:
                continue
            language_counts['sentences_with_lexical_evidence'] += 1
            language_counts['lexical_form_occurrences'] += len(hits)
            batch.append(row); focus_batch.append((row[0],canonical(hits)))
            if len(batch) >= 5000:
                work.executemany('INSERT INTO sentences VALUES (?,?,?,?,?)',batch)
                work.executemany('INSERT INTO focus VALUES (?,?)',focus_batch)
                work.commit(); batch=[]; focus_batch=[]
        work.executemany('INSERT INTO sentences VALUES (?,?,?,?,?)',batch)
        work.executemany('INSERT INTO focus VALUES (?,?)',focus_batch); work.commit()
        per_language[language] = dict(language_counts); counts.update(language_counts)
        print(canonical(dict(language=language,counts=language_counts,elapsed_s=round(time.monotonic()-started_scan,2))),flush=True)
        del automaton, forms
    # Both endpoints were selected strictly from development before any links
    # are joined. Link direction is canonical; no transitive translation use.
    queries=[]
    for name,path,_ in sources:
        work.execute('ATTACH DATABASE ? AS '+name,(path.resolve().as_uri()+'?mode=ro&immutable=1',))
        query='''SELECT a.id,a.language,fa.payload,b.id,b.language,fb.payload
        FROM sentences a JOIN '''+name+'''.links l ON l.a=a.id
        JOIN sentences b ON b.id=l.b JOIN focus fa ON fa.sentence=a.id JOIN focus fb ON fb.sentence=b.id
        WHERE a.language<>b.language'''
        parameters=[]
        if changed:
            marks=",".join("?" for _ in changed)
            query+=f" AND (a.language IN ({marks}) OR b.language IN ({marks}))"
            parameters=[*changed,*changed]
        queries.append((query,parameters))
    @lru_cache(maxsize=50000)
    def analyses(form_id):
        return json.loads(work.execute('SELECT analyses FROM lexicon WHERE id=?',(form_id,)).fetchone()[0])
    cached=lru_cache(maxsize=4000)(lambda payload:unique_hits(payload,analyses))
    batch=[];pair_counts=Counter()
    for aid, al, af, bid, bl, bf in (row for query,parameters in queries for row in work.execute(query,parameters)):
        counts['direct_development_pairs'] += 1
        left, right = cached(af), cached(bf)
        for sense in left.keys() & right.keys():
            a, b = left[sense], right[sense]
            if al != 'en' and bl != 'en' and not (a[5] and b[5]):
                counts['nonexplicit_pivot_excluded'] += 1; continue
            batch.append((aid,bid,sense,a[0],a[1],b[0],b[1],a[2],b[2],a[3],b[3],a[4],b[4]))
            counts['candidate_alignments'] += 1; pair_counts['-'.join(sorted([al,bl]))] += 1
        if len(batch) >= 10000:
            work.executemany('INSERT INTO alignments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',batch);work.commit();batch=[]
        if counts['direct_development_pairs'] % 100000 == 0:
            print(canonical(dict(stage='direct_links',counts=counts)),flush=True)
    work.executemany('INSERT INTO alignments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',batch);work.commit()
    if is_pgv:
        # Retain every source attribution and observed alignment for selected
        # development endpoints; these scores are not accuracy probabilities.
        work.executescript('''CREATE TABLE source_attribution AS SELECT p.* FROM corpus.attribution p JOIN sentences s ON s.id=p.sentence;
            CREATE TABLE source_link_evidence AS SELECT p.* FROM corpus.link_evidence p
                JOIN sentences a ON a.id=p.a JOIN sentences b ON b.id=p.b;''')
    work.execute("INSERT INTO sentence_search(sentence_search) VALUES ('rebuild')");work.commit()
    counts['distinct_aligned_senses'] = work.execute('SELECT count(DISTINCT sense) FROM alignments').fetchone()[0]
    counts['distinct_aligned_sentence_pairs'] = work.execute('SELECT count(*) FROM (SELECT a,b FROM alignments GROUP BY a,b)').fetchone()[0]
    result = dict(schema='vipi-broad-lexical-contexts-3',counts=dict(counts),languages=per_language,pairs=dict(pair_counts),
        lexical_focus_policy='whole supplied units or exact UTF-16 lexical focus inside indexed carriers; no whole-inflection meaning inference',
        complete=True,pilot=bool(args.max_sentences_per_language),max_sentences_per_language=args.max_sentences_per_language,
        changed_pair_languages=changed,direct_endpoint_selection_counts=endpoint_counts,
        source_catalog_sha256=sha_file(args.shards/'catalog.json'),source_release_id=catalog['release_id'],
        corpus_receipt_sha256=sha_file(args.corpus.parent/'receipt.json'),compiler_sha256=sha_file(Path(__file__)),
        corpus_sha256=input_receipt['sha256'],
        corpus_schema=input_receipt.get('schema','tatoeba-conversation-corpus'),
        automatic_sentence_alignment=is_pgv,
        supplemental_receipts=supplemental_receipts,
        corpus_partition='development',reserved_sentence_text_read=False,direct_links_only=True,
        independent_semantic_acceptance=False,runtime_integrated=False,
        sense_ids_are_candidate_links=True,
        meaning='Attributed candidate concordances; co-occurrence does not establish correct sense alignment.',
        licenses=['CC-BY-SA-4.0: dictionary evidence',sentence_license],
        dependencies=dict(pyahocorasick=importlib.metadata.version('pyahocorasick'),icu=icu.ICU_VERSION))
    work.execute('INSERT INTO metadata VALUES (?,?)',('receipt',canonical(result)));work.commit()
    assert work.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    work.close()
    for _,_,input_db in sources:input_db.close()
    result.update(bytes=context_path.stat().st_size,sha256=sha_file(context_path),seconds=round(time.monotonic()-started,2))
    write_json(args.output/'receipt.json',result)
    (args.output/'ATTRIBUTION.txt').write_text('Dictionary evidence: Wiktionary contributors, CC BY-SA 4.0; source links in senses.url.\n'
        +attribution+
        'Changes: Unicode-indexed lexical occurrences, direct development-pair concordances, FTS search.\n'
        'Generated candidates have not been independently accepted for runtime use.\n')
    print(canonical(result),flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('shards','corpus','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--language',action='append')
    parser.add_argument('--pair-language',action='append',help='Recompute only directly linked directions involving this changed language')
    parser.add_argument('--supplement',type=Path,action='append')
    parser.add_argument('--max-sentences-per-language',type=int,default=0)
    args=parser.parse_args();assert args.max_sentences_per_language>=0;build(args)
