#!/usr/bin/env python3
"""Index observed training-corpus word forms without inventing stems or approval.

All analyses of an ambiguous surface remain queryable. This is build-time
candidate evidence; it grants no runtime scope, translation or linguistic pass.
Each new snapshot gets its own output directory and pinned source receipts.
"""
import argparse
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
import sqlite3
from grammar_coverage import SOURCES,CONTENT,pack_key,sentences
from conversation_corpus import sha_file,write_json


def analyses(path,all_parts=False):
    for metadata,words in sentences(path):
        sentence=metadata.get('sent_id')
        if not sentence:raise ValueError('Attestation needs a source sentence ID')
        for token,form,lemma,pos,xpos,raw_features,head,relation,deps,misc in words:
            if not all_parts and (pos not in CONTENT or lemma=='_'):continue
            features={} if raw_features=='_' else dict(item.split('=',1) for item in raw_features.split('|'))
            yield (form,lemma,pos,json.dumps(features,sort_keys=True,separators=(',',':'))),{
                'sentence_id':sentence,'token_id':token,
                'sentence_sha256':hashlib.sha256(metadata.get('text','').encode()).hexdigest() if metadata.get('text') else None,
                'features_annotated':raw_features!='_',
                # Korean UD lemmas can encode multiple morphemes with '+'.
                # Such an analysis is not an atomic dictionary lookup alias.
                'atomic_lemma_candidate':lemma not in ('','_') and '+' not in lemma and not any(c.isspace() for c in lemma)}


def build(source,output,sources=SOURCES,all_parts=False):
    output.mkdir(parents=True,exist_ok=False);database=output/'attested-forms.sqlite'
    summaries=[]
    with sqlite3.connect(database) as db:
        db.executescript('''
PRAGMA application_id=1447645257;
PRAGMA user_version=1;
PRAGMA temp_store=FILE;
CREATE TABLE corpora(language TEXT PRIMARY KEY,repository TEXT NOT NULL,revision TEXT NOT NULL,
 receipt_sha256 TEXT NOT NULL,license TEXT NOT NULL,annotation_metadata TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE analyses(language TEXT NOT NULL,source_key TEXT NOT NULL,surface TEXT NOT NULL,
 lemma TEXT NOT NULL,lemma_key TEXT NOT NULL,pos TEXT NOT NULL,features TEXT NOT NULL,
 occurrences INTEGER NOT NULL,atomic_lemma_candidate INTEGER NOT NULL,evidence TEXT NOT NULL,
 PRIMARY KEY(language,source_key,surface,lemma,pos,features)) WITHOUT ROWID;
CREATE INDEX lemma_forms ON analyses(language,lemma_key,pos);
''')
        for language,repo,revision,filename in sources:
            folder=source/repo;receipt_path=folder/'receipt.json';receipt=json.loads(receipt_path.read_text())
            if receipt['commit']!=revision:raise ValueError('Wrong source revision')
            for asset in receipt['assets']:
                if sha_file(folder/asset['file'])!=asset['sha256']:raise ValueError('Changed source')
            readme=(folder/'README.md').read_text()
            if 'License: CC BY-SA 4.0' not in readme:raise ValueError('Unexpected license declaration')
            metadata={k:v for k,v in (line.split(': ',1) for line in readme.splitlines() if ': ' in line)
                if k in ('Genre','Lemmas','UPOS','Features','Relations')}
            db.execute('INSERT INTO corpora VALUES (?,?,?,?,?,?)',(language,repo,revision,sha_file(receipt_path),'CC BY-SA 4.0',json.dumps(metadata,sort_keys=True)))
            counts=Counter();examples=defaultdict(list);atomic={}
            for identity,evidence in analyses(folder/filename,all_parts=all_parts):
                counts[identity]+=1;atomic[identity]=evidence['atomic_lemma_candidate']
                if len(examples[identity])<3:examples[identity].append(evidence)
            for identity,count in sorted(counts.items()):
                form,lemma,pos,features=identity
                db.execute('INSERT INTO analyses VALUES (?,?,?,?,?,?,?,?,?,?)',
                    (language,pack_key(form),form,lemma,pack_key(lemma),pos,features,count,int(atomic[identity]),json.dumps(examples[identity],ensure_ascii=False,sort_keys=True)))
            ambiguous=db.execute('SELECT count(*) FROM (SELECT source_key FROM analyses WHERE language=? GROUP BY source_key HAVING count(DISTINCT lemma_key || char(31) || pos)>1)',(language,)).fetchone()[0]
            summaries.append({'language':language,'repository':repo,'revision':revision,'analyses':len(counts),
                'observed_tokens_with_lemma':sum(counts.values()),'ambiguous_surfaces':ambiguous,
                'atomic_nonidentity_analyses':sum(atomic[k] and pack_key(k[0])!=pack_key(k[1]) for k in counts),
                'annotation_metadata':metadata})
        db.commit();db.execute('VACUUM')
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Invalid SQLite output')
    (output/'ATTRIBUTION.txt').write_text('Universal Dependencies contributors, CC BY-SA 4.0.\n'
        'https://creativecommons.org/licenses/by-sa/4.0/\n'
        'Exact repository revisions, authors, licenses and source files are retained in the source receipts.\n'
        'Changes: indexed observed forms, lemmas, annotations and bounded source references.\n'
        'Not a translation dictionary; annotations and derived analyses require contextual qualification.\n')
    receipt={'schema':'vipi-attested-forms-build-1','compiler_sha256':sha_file(Path(__file__)),
        'analysis_scope':'all_observed_ud_parts_of_speech' if all_parts else 'content_parts_of_speech_only',
        'unknown_lemma_analyses_retained':all_parts,
        'parser_sha256':sha_file(Path(__file__).with_name('grammar_coverage.py')),
        'database_sha256':sha_file(database),'bytes':database.stat().st_size,'languages':summaries,
        'runtime_integration':False,'linguistic_acceptance':False,'release_ready':False,
        'limits':['Official train splits only; Arabic absent; mixed genres are not representative chat.',
            'Competing lemmas/POS/features within the declared analysis scope are retained; frequency never resolves a sense.',
            'Known lemmas cannot authorize stripping particles or changing person, possession, negation, tense or number.',
            'Source annotation quality varies; Korean composite lemmas are not atomic lookup aliases.',
            'No target translations, readings or bilingual grammatical equivalences are inferred.']}
    write_json(output/'receipt.json',receipt);return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--all-parts-of-speech',action='store_true')
    a=p.parse_args();r=build(a.source,a.output,all_parts=a.all_parts_of_speech)
    print(json.dumps({k:v for k,v in r.items() if k not in ('limits','languages')}|{'languages':len(r['languages']),'analyses':sum(x['analyses'] for x in r['languages'])}))
