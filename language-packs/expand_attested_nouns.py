#!/usr/bin/env python3
"""Qualify candidate plural-noun supplements from observed UD analyses.

This is a build-time experiment, not a stemmer or linguistic approval. All
observed POS/lemma/number alternatives must agree before a form is proposed.
Original dictionary senses, including senses without targets, remain vetoes.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import shutil
import sqlite3
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import ec
from build_wiktextract import canonical,digest_file
from context_hints import lookup_key,native_grammar
from export_bilingual import CATALOG_SHA256

LANGUAGES=('en','es','fr','de','it','pt')
POLICY='attested-unanimous-noun-plural-candidates-1'


def noun_forms(connection,language):
    by_surface=defaultdict(list)
    for row in connection.execute('SELECT source_key,surface,lemma,lemma_key,pos,features,occurrences,atomic_lemma_candidate,evidence FROM analyses WHERE language=?',(language,)):
        by_surface[row[0]].append({'surface':row[1],'lemma':row[2],'lemma_key':row[3],'pos':row[4],
            'features':json.loads(row[5]),'occurrences':row[6],'atomic':bool(row[7]),'evidence':json.loads(row[8])})
    plural={};lemma_plurals=defaultdict(list);noun_lemmas={}
    for key,rows in by_surface.items():
        lemmas={r['lemma_key'] for r in rows}
        if len(lemmas)!=1 or any(r['pos']!='NOUN' or not r['atomic'] for r in rows):continue
        lemma=next(iter(lemmas));noun_lemmas[key]=lemma
        if any(r['features'].get('Number')!='Plur' for r in rows):continue
        # No punctuation, whitespace or embedded compounds are inferred.
        if not key.isalpha() or not 2<=len(key)<=64:continue
        value={'lemma':lemma,'analyses':rows,'occurrences':sum(r['occurrences'] for r in rows)}
        plural[key]=value;lemma_plurals[lemma].append(key)
    return plural,lemma_plurals,noun_lemmas


def augment(database,catalog,source,target,source_forms,target_forms,grammar,maximum):
    source_plural,_,_=source_forms;target_plural,target_by_lemma,target_noun_lemmas=target_forms
    summary={'source':source,'target':target,'proposed_sources':0,'added_mappings':0,'retained_competing_claims':0}
    with sqlite3.connect(database) as db:
        db.execute('PRAGMA temp_store=FILE')
        db.execute('CREATE TABLE attested_noun_forms(language TEXT NOT NULL,form TEXT NOT NULL,evidence TEXT NOT NULL,PRIMARY KEY(language,form)) WITHOUT ROWID')
        db.execute('ATTACH DATABASE ? AS catalog',(catalog.resolve().as_uri()+'?mode=ro&immutable=1',))
        existing={row[0] for row in db.execute('SELECT DISTINCT source FROM vocabulary')}
        # Snapshot original rows: newly proposed forms cannot recursively seed
        # more forms, and dictionary qualifications must not be generalized.
        seeds=defaultdict(list)
        for row in db.execute("SELECT v.source,v.target,v.sense_id,v.reading FROM vocabulary v JOIN senses s ON s.id=v.sense_id WHERE s.part_of_speech='noun' AND v.mapping_details='{}'"):
            seeds[row[0]].append(row[1:])
        proposals=[]
        for surface,value in sorted(source_plural.items(),key=lambda item:(-item[1]['occurrences'],item[0])):
            lemma=value['lemma']
            if surface in existing or surface==lemma or native_grammar(surface,source,grammar[source]):continue
            mappings={}
            for target_base,sense,reading in seeds.get(lemma,[]):
                base=lookup_key(target_base,target)
                target_lemma=target_noun_lemmas.get(base,base)
                for form in target_by_lemma.get(target_lemma,[]):
                    if form==surface or native_grammar(form,target,grammar[target]):continue
                    # Keep attested capitalization; German noun case must not
                    # be replaced with an invented lowercase written form.
                    for written in sorted({r['surface'] for r in target_plural[form]['analyses']}):
                        mappings[(written,sense)]={'source_form':surface,'target_form':form,
                            'dictionary_source':lemma,'dictionary_target':target_base,'policy':POLICY}
            if not mappings:continue
            proposals.append((surface,lemma,mappings))
            if len(proposals)>=maximum:break
        for surface,lemma,mappings in proposals:
            db.execute('INSERT OR IGNORE INTO attested_noun_forms VALUES (?,?,?)',(source,surface,canonical(source_plural[surface])))
            for evidence in mappings.values():
                form=evidence['target_form']
                db.execute('INSERT OR IGNORE INTO attested_noun_forms VALUES (?,?,?)',(target,form,canonical(target_plural[form])))
            db.executemany('INSERT OR IGNORE INTO vocabulary VALUES (?,?,?,?,?)',
                [(surface,written,sense,'',canonical({'inflection_candidate':evidence}))
                 for (written,sense),evidence in mappings.items()])
            # Preserve every base-lemma claim, including non-nouns and senses
            # with no usable target. Also import all catalog claims for the
            # inflected spelling: plurals can have lexicalized new meanings.
            db.execute('INSERT OR IGNORE INTO source_senses SELECT ?,sense_id FROM source_senses WHERE source=?',(surface,lemma))
            db.execute('''INSERT OR IGNORE INTO source_senses SELECT ?,sense_id FROM catalog.terms
                WHERE language=? AND normalized=?''',(surface,source,surface))
            summary['proposed_sources']+=1;summary['added_mappings']+=len(mappings)
        db.execute('''INSERT OR IGNORE INTO senses SELECT s.id,s.label,s.part_of_speech,s.source_word,s.source_line,s.source_url,
            'attested-form-source-ambiguity-veto-only' FROM catalog.senses s
            WHERE s.id IN (SELECT sense_id FROM source_senses)''')
        # Newly imported rival senses get no positive cue; absence of a cue
        # cannot remove their ambiguity claim. Existing base cues are retained.
        for surface,lemma,mappings in proposals:
            summary['retained_competing_claims']+=db.execute('SELECT count(*) FROM source_senses WHERE source=?',(surface,)).fetchone()[0]
        uncovered=db.execute('''SELECT count(*) FROM vocabulary v WHERE NOT EXISTS
            (SELECT 1 FROM source_senses s WHERE s.source=v.source AND s.sense_id=v.sense_id)''').fetchone()[0]
        if uncovered or db.execute('PRAGMA foreign_key_check').fetchone():raise ValueError('Incomplete sense evidence')
        db.commit()
    return summary


def main(a):
    if not 1<=a.maximum_sources<=1000 or a.revision<1:raise ValueError('Bounded positive revision required')
    receipt=json.loads((a.forms/'receipt.json').read_text());forms_db=a.forms/'attested-forms.sqlite'
    if receipt.get('analysis_scope')!='all_observed_ud_parts_of_speech' or receipt.get('unknown_lemma_analyses_retained') is not True:
        raise ValueError('All observed POS, including unknown lemmas, are required')
    if digest_file(forms_db)!=receipt['database_sha256'] or digest_file(a.catalog)!=CATALOG_SHA256:raise ValueError('Changed source evidence')
    guard=json.loads(a.grammar.read_text())
    if guard.get('schema')!='vipi-native-grammar-guard-1':raise ValueError('Grammar evidence required')
    pairs=[tuple(pair.split('-')) for pair in a.pair] if a.pair else [(s,t) for s in LANGUAGES for t in LANGUAGES if s!=t]
    if len(set(pairs))!=len(pairs) or any(s not in LANGUAGES or t not in LANGUAGES or s==t for s,t in pairs):raise ValueError('Invalid noun-plural qualification pairs')
    with sqlite3.connect(forms_db.resolve().as_uri()+'?mode=ro&immutable=1',uri=True) as db:
        forms={lang:noun_forms(db,lang) for lang in sorted({x for pair in pairs for x in pair})}
    a.output.mkdir(parents=True,exist_ok=False);key=ec.generate_private_key(ec.SECP256R1())
    (a.output/'signing-public-key.der').write_bytes(key.public_key().public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo))
    summaries=[]
    for source,target in pairs:
        identifier=source+'-'+target;base=a.base/identifier;folder=a.output/identifier;folder.mkdir()
        manifest=json.loads((base/'manifest.json').read_text())
        if manifest['catalog_sha256']!=CATALOG_SHA256 or manifest['schema_version']!=4 or manifest['context_policy']!='all-source-senses-veto-3':raise ValueError('Wrong base pack')
        if manifest['revision']>=a.revision or digest_file(base/'vocabulary.sqlite')!=manifest['sha256']:raise ValueError('Changed/newer base')
        if manifest['grammar_guard_sha256']!=digest_file(a.grammar):raise ValueError('Changed grammar evidence')
        database=folder/'vocabulary.sqlite';shutil.copyfile(base/'vocabulary.sqlite',database)
        summary=augment(database,a.catalog,source,target,forms[source],forms[target],guard['terms'],a.maximum_sources)
        with sqlite3.connect(database) as db:
            db.execute('UPDATE metadata SET value=? WHERE key=?',(str(a.revision),'revision'))
            db.execute('INSERT INTO metadata VALUES (?,?)',('inflection_policy',POLICY))
            db.commit();db.execute('VACUUM')
            if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Bad SQLite output')
            manifest['mappings'],manifest['headwords']=db.execute('SELECT count(*),count(DISTINCT source) FROM vocabulary').fetchone()
            manifest['unmapped_source_senses']=db.execute('''SELECT count(*) FROM source_senses s WHERE NOT EXISTS
                (SELECT 1 FROM vocabulary v WHERE v.source=s.source AND v.sense_id=s.sense_id)''').fetchone()[0]
        if database.stat().st_size>67108864:raise ValueError('Native pack size bound exceeded')
        manifest.update(revision=a.revision,sha256=digest_file(database),bytes=database.stat().st_size,
            key_id=a.key_id,base_manifest_sha256=digest_file(base/'manifest.json'),inflection_policy=POLICY,
            inflection_compiler_sha256=digest_file(Path(__file__)),attested_forms_sha256=receipt['database_sha256'],
            inflection_candidates=summary,release_ready=False,linguistic_acceptance=False)
        encoded=canonical(manifest).encode();signature=key.sign(encoded,ec.ECDSA(hashes.SHA256()))
        key.public_key().verify(signature,encoded,ec.ECDSA(hashes.SHA256()))
        (folder/'manifest.json').write_bytes(encoded);(folder/'manifest.sig').write_bytes(signature)
        (folder/'ATTRIBUTION.txt').write_text((base/'ATTRIBUTION.txt').read_text()+'\n'+(a.forms/'ATTRIBUTION.txt').read_text()+'\nChanges: candidate plural noun forms; vocabulary.mapping_details references attested_noun_forms evidence. Not linguistic approval.\n')
        summary.update(bytes=manifest['bytes'],sha256=manifest['sha256']);summaries.append(summary);print(canonical(summary),flush=True)
    (a.output/'receipt.json').write_text(canonical({'schema':'vipi-attested-noun-supplement-1','pairs':summaries,
        'forms_receipt_sha256':digest_file(a.forms/'receipt.json'),'compiler_sha256':digest_file(Path(__file__)),
        'qualification_only_key':True,'private_key_written':False,'linguistic_acceptance':False,'release_ready':False,
        'limits':['Observed UD analyses are not exhaustive or automatically correct. Missing evidence abstains.',
            'Plural noun proposals only; no verbs, pronouns, particle stripping, new readings or target-text generation.',
            'Dictionary senses remain candidates. Source/target attestation does not prove bilingual contextual equivalence.',
            'No production integration or majority-conversation claim.']})+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('base','forms','catalog','grammar','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--revision',type=int,required=True);p.add_argument('--key-id',required=True)
    p.add_argument('--maximum-sources',type=int,default=250);p.add_argument('--pair',action='append',default=[])
    main(p.parse_args())
