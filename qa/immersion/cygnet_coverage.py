#!/usr/bin/env python3
"""Measure the pinned concept network; counts are not language acceptance."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sqlite3
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'language-packs'))
from build_wiktextract import digest_file, form_ok
from context_hints import lookup_key, native_grammar

LANGUAGES = {'en':'en','es':'es','fr':'fr','de':'de','it':'it','pt':'pt',
             'ar':'arb','zh':'cmn-Hans','ja':'ja','ko':'ko'}


def main(args):
    args.output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    receipt = json.loads((args.source/'receipt.json').read_text())
    for asset in receipt['assets']:
        path = args.source/asset['database']
        if path.stat().st_size != asset['uncompressed_bytes'] or digest_file(path) != asset['database_sha256']:
            raise ValueError('Research source hash/size mismatch')
    grammar = json.loads(args.grammar_guard.read_text())['terms']
    reverse = {value:key for key,value in LANGUAGES.items()}
    db = sqlite3.connect((args.source/'cygnet.db').resolve().as_uri()+'?mode=ro&immutable=1', uri=True)
    db.execute('PRAGMA trusted_schema=OFF')
    concepts = {language:defaultdict(set) for language in LANGUAGES}
    forms = {language:set() for language in LANGUAGES}
    native_definitions = {language:set() for language in LANGUAGES}
    native_examples = {language:set() for language in LANGUAGES}
    counts = Counter(); languages = []; probes = []
    marks = ','.join('?' for _ in LANGUAGES)
    sql = '''SELECT l.code,f.form,s.synset_rowid,f.rank,e.pos FROM forms f
      JOIN entries e ON e.rowid=f.entry_rowid JOIN languages l ON l.rowid=e.language_rowid
      JOIN senses s ON s.entry_rowid=e.rowid WHERE l.code IN ('''+marks+')'
    for code, form, concept, rank, pos in db.execute(sql, list(LANGUAGES.values())):
        language = reverse[code]
        if pos not in ('NOUN','VERB','ADJ','ADV','ADJ_SAT','INTJ'):
            counts['excluded_pos_rows'] += 1; continue
        # Upstream normalized_form removes accents. Recompute our own exact
        # NFC/lower key from the original, retaining distinctions such as si/sí.
        if not form_ok(form):
            counts['unsupported_surface_rows'] += 1; continue
        if native_grammar(form, language, grammar[language]):
            counts['grammar_rows'] += 1; continue
        key = lookup_key(form, language)
        concepts[language][concept].add(key); forms[language].add(key)
        counts['retained_form_sense_rows'] += 1
        if rank: counts['nonlemma_form_sense_rows'] += 1
    for code, concept in db.execute('''SELECT l.code,d.synset_rowid FROM definitions d
      JOIN languages l ON l.rowid=d.language_rowid WHERE l.code IN ('''+marks+')', list(LANGUAGES.values())):
        native_definitions[reverse[code]].add(concept)
    for code, concept in db.execute('''SELECT l.code,s.synset_rowid FROM sense_examples x
      JOIN senses s ON s.rowid=x.sense_rowid JOIN entries e ON e.rowid=s.entry_rowid
      JOIN languages l ON l.rowid=e.language_rowid WHERE l.code IN ('''+marks+')', list(LANGUAGES.values())):
        # The example is linked to a source sense. Its actual text/language
        # still requires inspection; a link is not alignment or correctness.
        native_examples[reverse[code]].add(concept)
    with sqlite3.connect(args.catalog.resolve().as_uri()+'?mode=ro&immutable=1',uri=True) as old:
        for language in LANGUAGES:
            existing = {lookup_key(form,language) for form, in old.execute('SELECT DISTINCT form FROM terms WHERE language=?',(language,))}
            known = set(concepts[language])
            languages.append({'language':language,'upstream_language':LANGUAGES[language],
                'forms':len(forms[language]),'concepts':len(known),
                'form_concept_links':sum(map(len,concepts[language].values())),
                'forms_absent_from_existing_catalog':len(forms[language]-existing),
                'concepts_with_native_definition':len(known & native_definitions[language]),
                'concepts_with_source_sense_example':len(known & native_examples[language])})
    pairs=[]
    for source in LANGUAGES:
        for target in LANGUAGES:
            if source == target: continue
            shared = concepts[source].keys() & concepts[target].keys()
            source_forms = set().union(*(concepts[source][concept] for concept in shared)) if shared else set()
            pairs.append({'pair':source+'-'+target,'shared_concepts':len(shared),
                'source_forms':len(source_forms),
                'form_pairs_counted_per_concept':sum(len(concepts[source][c])*len(concepts[target][c]) for c in shared),
                'concepts_with_source_context':len(shared & (native_definitions[source] | native_examples[source]))})
    for language, word in [('es','lectura'),('en','reading'),('de','Bank')]:
        rows=[]
        sql='''SELECT DISTINCT s.rowid,s.synset_rowid,y.ili,e.pos FROM forms f
          JOIN entries e ON e.rowid=f.entry_rowid JOIN languages l ON l.rowid=e.language_rowid
          JOIN senses s ON s.entry_rowid=e.rowid JOIN synsets y ON y.rowid=s.synset_rowid
          WHERE f.normalized_form=? AND f.form=? AND l.code=?'''
        for sid,cid,ili,pos in db.execute(sql,(word.lower(),word,LANGUAGES[language])):
            gloss=db.execute("SELECT definition FROM definitions d JOIN languages l ON l.rowid=d.language_rowid WHERE d.synset_rowid=? AND l.code='en'",(cid,)).fetchall()
            targets=db.execute("SELECT l.code,f.form FROM senses s JOIN entries e ON e.rowid=s.entry_rowid JOIN languages l ON l.rowid=e.language_rowid JOIN forms f ON f.entry_rowid=e.rowid WHERE s.synset_rowid=? AND f.rank=0 AND l.code IN ('en','ja','ko','fr')",(cid,)).fetchall()
            examples=db.execute('SELECT x.example FROM examples x JOIN sense_examples se ON se.example_rowid=x.rowid WHERE se.sense_rowid=? LIMIT 3',(sid,)).fetchall()
            rows.append({'sense':sid,'concept':cid,'ili':ili,'pos':pos,'english_definitions':gloss,'targets':targets,'source_examples':examples})
        probes.append({'language':language,'word':word,'senses':rows})
    resources=[dict(zip(('code','version','language','license','url','confidence_score'), row)) for row in db.execute('''SELECT r.code,r.version,l.code,r.licence,r.url,r.confidence_score
        FROM resources r LEFT JOIN languages l ON l.rowid=r.language_rowid
        WHERE l.code IN ('''+marks+") OR r.code='cili'",list(LANGUAGES.values()))]
    db.close()
    result = {'source_receipt_sha256':digest_file(args.source/'receipt.json'),
              'catalog_sha256':digest_file(args.catalog),'compiler_sha256':digest_file(Path(__file__)),
              'grammar_guard_sha256':digest_file(args.grammar_guard),
              'context_compiler_sha256':digest_file(Path(__file__).resolve().parents[2]/'language-packs/context_hints.py'),
              'runtime_integration':False,'linguistic_acceptance':False,
              'limits':['A shared concept supplies candidate semantic evidence, not interchangeable inflected phrases.',
                        'No per-row licensing acceptance or frequency/register ranking yet.',
                        'Pronunciations are not certified romanizations; none counted as display-ready.',
                        'Source-language sense examples are not assumed aligned to target forms.',
                        'Unmapped source meanings remain necessary even when a pair has no target for them.'],
              'languages':languages,'pairs':pairs,'resources':resources,'probes':probes,
              'counts':dict(counts),'seconds':time.monotonic()-started}
    (args.output/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'languages':languages,'pairs':len(pairs),'minimum_pair':min(pairs,key=lambda x:x['source_forms']),
                      'seconds':result['seconds']},ensure_ascii=False))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source','grammar-guard','catalog','output'): parser.add_argument('--'+name,type=Path,required=True)
    main(parser.parse_args())
