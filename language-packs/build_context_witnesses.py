#!/usr/bin/env python3
"""Compile local word/context evidence from attributed direct references.

This is an experimental selector input. Counts measure reference agreement,
not a calibrated probability of correctness or independent semantic acceptance.
Dictionary sense labels are deliberately not treated as training truth.
"""
import argparse
from collections import Counter
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time
import icu
from build_wiktextract import canonical,digest_file
from context_hints import lookup_key,GRAMMAR


def compile(args):
    started=time.monotonic();args.output.mkdir(parents=True,exist_ok=False)
    parent=json.loads((args.contexts.parent/'receipt.json').read_text())
    assert parent['complete'] and not parent['pilot'] and parent['schema'] in {'vipi-broad-lexical-contexts-2','vipi-broad-lexical-contexts-3'}
    assert digest_file(args.contexts)==parent['sha256']
    inputs=[(args.contexts,parent)]
    release=parent['source_release_id'];proof=None
    additional=getattr(args,'additional_context',None)
    if additional:
        # The first extension has a separate negative-ID namespace and a full
        # normalized-text exclusion index over all prior source partitions.
        # Do not generalize this to unproven overlapping corpora.
        delta=json.loads((additional.parent/'receipt.json').read_text())
        assert delta['complete'] and not delta['pilot'] and delta['schema']=='vipi-broad-lexical-contexts-3'
        assert digest_file(additional)==delta['sha256']
        assert delta['corpus_schema']=='vipi-pgv-corpus-1'
        delta_corpus=json.loads(args.additional_corpus_receipt.read_text())
        assert digest_file(args.additional_corpus_receipt)==delta['corpus_receipt_sha256']
        assert delta_corpus['sha256']==delta['corpus_sha256'] and delta_corpus['direct_links_only']
        exclusion=json.loads((args.source_exclusions.parent/'receipt.json').read_text())
        assert exclusion['complete'] and digest_file(args.source_exclusions)==exclusion['sha256']==delta_corpus['exclusions_sha256']
        assert exclusion['source_corpus_sha256']==parent['corpus_sha256']
        assert exclusion['source_corpus_receipt_sha256']==parent['corpus_receipt_sha256']
        supplements={digest_file(p):json.loads(p.read_text()) for p in args.base_supplement_receipt}
        for row in parent.get('supplemental_receipts',[]):
            supplementary=supplements[row['receipt_sha256']]
            assert supplementary['sha256']==row['corpus_sha256']
            assert supplementary['schema']=='vipi-swahili-development-supplement-1'
            assert supplementary['swahili_source_sha256']==exclusion['swahili_source_sha256']
        adapter_sha=None
        if release!=delta['source_release_id']:
            assert args.release_adapter, 'Different dictionary releases require a verified adapter'
            adapter=json.loads((args.release_adapter.parent/'receipt.json').read_text())
            assert digest_file(args.release_adapter)==adapter['sha256']
            assert adapter['adaptation_policy']=='unchanged-dictionary-links-added-carriers-1'
            assert adapter['source_contexts_sha256']==parent['sha256']
            assert adapter['context_compilation_release_id']==release
            assert adapter['source_release_id']==delta['source_release_id']
            assert all(v['senses_added']==0 and v['terms_added']==0 for v in adapter['adaptation_proof'].values())
            adapter_sha=adapter['sha256']
        else:
            # A fresh recomputation of both corpora uses one exact dictionary
            # release and catalog. No old dictionary evidence is rebound here.
            assert parent['source_catalog_sha256']==delta['source_catalog_sha256']
        release=delta['source_release_id'];inputs.append((additional,delta))
        proof=dict(exclusions_sha256=exclusion['sha256'],release_adapter_sha256=adapter_sha,
            same_dictionary_catalog_sha256=parent['source_catalog_sha256'] if adapter_sha is None else None,
            base_supplement_receipts=sorted(supplements),policy='all prior source text excluded; positive base IDs and negative PGV IDs')
    extra_contexts=getattr(args,'extra_context',[]) or []
    extra_receipts=getattr(args,'extra_corpus_receipt',[]) or []
    assert len(extra_contexts)==len(extra_receipts)
    # The supported third source is the pinned MASSIVE import. Its importer
    # excludes the complete Tatoeba/Swahili index, PGV corpus and evaluation
    # identities. A different source requires its own verified proof.
    if extra_contexts:
        assert additional and len(extra_contexts)==1 and not args.release_adapter
        extra_path,extra_receipt_path=extra_contexts[0],extra_receipts[0]
        extra=json.loads((extra_path.parent/'receipt.json').read_text())
        extra_corpus=json.loads(extra_receipt_path.read_text())
        assert extra['complete'] and not extra['pilot'] and extra['schema']=='vipi-broad-lexical-contexts-3'
        assert digest_file(extra_path)==extra['sha256']
        assert extra['corpus_schema']==extra_corpus['schema']=='vipi-massive-corpus-1'
        assert extra_corpus['complete'] and extra_corpus['policy']=='massive-original-train-direct-unlocalized-1'
        assert digest_file(extra_receipt_path)==extra['corpus_receipt_sha256']
        assert extra_corpus['sha256']==extra['corpus_sha256']
        assert extra_corpus['prior_corpus_sha256']==delta_corpus['sha256']
        assert extra_corpus['exclusions_sha256']==exclusion['sha256']
        assert extra_corpus['evaluation_exclusions'] and extra_corpus['evaluation_hashes']>0
        assert extra['source_release_id']==release
        assert extra['source_catalog_sha256']==parent['source_catalog_sha256']==delta['source_catalog_sha256']
        inputs.append((extra_path,extra))
        proof['additional_sources']=[dict(schema=extra_corpus['schema'],contexts_sha256=extra['sha256'],
            corpus_sha256=extra_corpus['sha256'],corpus_receipt_sha256=digest_file(extra_receipt_path),
            prior_corpus_sha256=extra_corpus['prior_corpus_sha256'],
            exclusions_sha256=extra_corpus['exclusions_sha256'],
            evaluation_exclusions=extra_corpus['evaluation_exclusions'],
            policy=extra_corpus['policy'])]
    selected={tuple(pair.split('-')) for pair in args.pair}
    languages={language for _,receipt in inputs for language in receipt['languages']}
    assert selected and all(len(pair)==2 and pair[0]!=pair[1] and all(x in languages for x in pair) for pair in selected)
    sources=[]
    for index,(path,_) in enumerate(inputs):
        source=sqlite3.connect(path.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
        source.execute('PRAGMA temp_store=FILE');source.execute('PRAGMA cache_size=-32768')
        lower,upper=source.execute('SELECT min(id),max(id) FROM sentences').fetchone()
        assert lower is not None
        if additional:assert lower>0 if index==0 else upper<0
        # Every source occupies a separate signed integer interval. This also
        # rejects accidental ID overlap before any evidence is accumulated.
        assert all(upper<lo or lower>hi for _,lo,hi in sources), 'Overlapping source identity intervals'
        sources.append((source,lower,upper))
    work_path=args.output/'observations.sqlite';work=sqlite3.connect(work_path)
    work.executescript('''PRAGMA temp_store=FILE;PRAGMA cache_size=-32768;
        CREATE TABLE atoms(id INTEGER PRIMARY KEY,value TEXT NOT NULL UNIQUE);
        CREATE TABLE pairs(id INTEGER PRIMARY KEY,source TEXT NOT NULL,target TEXT NOT NULL,UNIQUE(source,target));
        CREATE TABLE observations(pair INTEGER NOT NULL,word INTEGER NOT NULL,cue INTEGER NOT NULL,target INTEGER NOT NULL,
            sentence INTEGER NOT NULL,counterpart INTEGER NOT NULL,PRIMARY KEY(pair,word,cue,target,sentence)) WITHOUT ROWID;''')
    for i,(left,right) in enumerate(sorted(selected),1):work.execute('INSERT INTO pairs VALUES (?,?,?)',(i,left,right))
    pairs={(a,b):i for i,a,b in work.execute('SELECT * FROM pairs')};atoms={}
    def atom(value):
        if value not in atoms:
            atoms[value]=len(atoms)+1;work.execute('INSERT INTO atoms VALUES (?,?)',(atoms[value],value))
        return atoms[value]
    @lru_cache(maxsize=12000)
    def sentence(identifier):
        matches=[db.execute('SELECT language,text,owner FROM sentences WHERE id=?',(identifier,)).fetchone()
            for db,lower,upper in sources if lower<=identifier<=upper]
        matches=[row for row in matches if row is not None];assert len(matches)==1
        language,text,owner=matches[0]
        iterator=icu.BreakIterator.createWordInstance(icu.Locale(language));value=icu.UnicodeString(text);iterator.setText(value)
        words=[];start=iterator.first()
        for end in iterator:
            token=str(value[start:end])
            if any(c.isalpha() for c in token):words.append((start,end,lookup_key(token,language)))
            start=end
        return language,text,owner,words
    @lru_cache(maxsize=50000)
    def focus(identifier,start,end):
        language,text,_,words=sentence(identifier);value=icu.UnicodeString(text)
        term=lookup_key(str(value[start:end]),language)
        if not term or term in GRAMMAR.get(language,set()) or len(term)>128:return None
        # Full-message agreement is a separate feature for short responses;
        # ordinary cues come from the same clause and retain their side.
        outside=[row for row in words if row[1]<=start or row[0]>=end]
        cues=set()
        if not outside:cues.add('@whole')
        left=[row for row in words if row[1]<=start][-6:]
        right=[row for row in words if row[0]>=end][:6]
        for a,b,word in left:
            if any(c in '.!?。！？;；\r\n' for c in str(value[b:start])):continue
            if word!=term and word not in GRAMMAR.get(language,set()):cues.add('L:'+word)
        for a,b,word in right:
            if any(c in '.!?。！？;；\r\n' for c in str(value[end:a])):continue
            if word!=term and word not in GRAMMAR.get(language,set()):cues.add('R:'+word)
        return language,term,sorted(cues)
    counts=Counter();batch=[]
    # Remove candidate sense-label duplication before collecting evidence.
    # Word/context agreement is not a claim that one dictionary label is true.
    query='''SELECT DISTINCT m.a,m.b,m.a_start,m.a_end,m.b_start,m.b_end
        FROM alignments m JOIN sentences a ON a.id=m.a JOIN sentences b ON b.id=m.b
        WHERE '''+' OR '.join('(a.language=? AND b.language=?)' for _ in selected|{(b,a) for a,b in selected})
    arguments=[x for pair in sorted(selected|{(b,a) for a,b in selected}) for x in pair]
    for a,b,sa,se,ta,te in (row for db,_,_ in sources for row in db.execute(query,arguments)):
        counts['distinct_reference_spans']+=1
        left=focus(a,sa,se);right=focus(b,ta,te)
        if not left or not right:continue
        for one,two,sid,tid in [(left,right,a,b),(right,left,b,a)]:
            language,word,cues=one;target_language,target,_=two
            pair=pairs.get((language,target_language))
            if not pair or word==target:continue
            for cue in cues:batch.append((pair,atom(word),atom(cue),atom(target),sid,tid))
        if len(batch)>=20000:
            work.executemany('INSERT OR IGNORE INTO observations VALUES (?,?,?,?,?,?)',batch);work.commit();batch=[]
        if counts['distinct_reference_spans']%100000==0:
            print(canonical(dict(stage='references',counts=counts)),flush=True)
    work.executemany('INSERT OR IGNORE INTO observations VALUES (?,?,?,?,?,?)',batch);work.commit()
    counts['distinct_observations']=work.execute('SELECT count(*) FROM observations').fetchone()[0]
    work.executescript('''CREATE TABLE frequencies AS SELECT pair,word,cue,target,count(*) AS support FROM observations GROUP BY pair,word,cue,target;
        CREATE INDEX frequencies_lookup ON frequencies(pair,word,cue,target);
        CREATE TABLE totals AS SELECT pair,word,cue,sum(support) AS total FROM frequencies GROUP BY pair,word,cue;
        CREATE UNIQUE INDEX totals_lookup ON totals(pair,word,cue);''')
    output_path=args.output/'witnesses.sqlite';output=sqlite3.connect(output_path)
    output.executescript('''PRAGMA application_id=1447645257;PRAGMA user_version=11;
        CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL) WITHOUT ROWID;
        CREATE TABLE witnesses(source TEXT NOT NULL,target TEXT NOT NULL,word TEXT NOT NULL,counterpart TEXT NOT NULL,
            cue TEXT NOT NULL,support INTEGER NOT NULL,total INTEGER NOT NULL,
            PRIMARY KEY(source,target,word,counterpart,cue)) WITHOUT ROWID;
        CREATE TABLE references_used(sentence INTEGER PRIMARY KEY,owner TEXT NOT NULL);
        CREATE TABLE evidence(source TEXT NOT NULL,target TEXT NOT NULL,word TEXT NOT NULL,counterpart TEXT NOT NULL,cue TEXT NOT NULL,
            sentence INTEGER NOT NULL,translation INTEGER NOT NULL,
            PRIMARY KEY(source,target,word,counterpart,cue,sentence)) WITHOUT ROWID;''')
    rows=work.execute('''SELECT p.source,p.target,w.value,t.value,c.value,f.support,z.total,f.pair,f.word,f.cue,f.target
        FROM frequencies f JOIN totals z USING(pair,word,cue) JOIN pairs p ON p.id=f.pair
        JOIN atoms w ON w.id=f.word JOIN atoms t ON t.id=f.target JOIN atoms c ON c.id=f.cue
        WHERE f.support>=? AND f.support*1.0/z.total>=? ORDER BY p.id,f.word,f.target,f.cue''',(args.minimum_support,args.minimum_agreement))
    by_pair=Counter();references=set()
    for left,right,word,target,cue,n,total,pair,w,c,t in rows:
        output.execute('INSERT INTO witnesses VALUES (?,?,?,?,?,?,?)',(left,right,word,target,cue,n,total));by_pair[left+'-'+right]+=1
        # Stable traceable examples support later inspection. Aggregate counts
        # use every distinct source sentence, not just these retained examples.
        for sid,tid in work.execute('SELECT sentence,counterpart FROM observations WHERE pair=? AND word=? AND cue=? AND target=? ORDER BY sentence LIMIT 3',(pair,w,c,t)):
            output.execute('INSERT INTO evidence VALUES (?,?,?,?,?,?,?)',(left,right,word,target,cue,sid,tid));references.update([sid,tid])
    for identifier in sorted(references):
        output.execute('INSERT INTO references_used VALUES (?,?)',(identifier,sentence(identifier)[2]))
    counts['witnesses']=sum(by_pair.values());counts['attributed_sentences']=len(references)
    metadata=dict(schema='vipi-context-witnesses-1',policy='experimental-direct-reference-agreement-1',
        source_contexts_sha256=parent['sha256'],source_release_id=release,
        additional_contexts_sha256=[receipt['sha256'] for _,receipt in inputs[1:]],disjoint_source_proof=proof,
        minimum_support=args.minimum_support,minimum_agreement=args.minimum_agreement,
        counts=dict(counts),pairs=dict(by_pair),compiler_sha256=digest_file(Path(__file__)),
        requested_pairs=['-'.join(pair) for pair in sorted(selected)],
        independent_semantic_acceptance=False,release_ready=False,
        warning='Reference agreement is not a calibrated correctness probability. Dictionary sense IDs are not classifier labels.',
        cue_policy='up to six original ICU words on each side in the same clause, or whole lexical message',
        license='; '.join(dict.fromkeys(v for _,receipt in inputs for v in receipt.get('licenses',['CC BY 2.0 FR','dictionary evidence provenance CC-BY-SA-4.0']))),
        automatic_sentence_alignment=any(receipt.get('automatic_sentence_alignment',False) for _,receipt in inputs))
    output.executemany('INSERT INTO metadata VALUES (?,?)',[(k,canonical(v)) for k,v in metadata.items()]);output.commit()
    assert output.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    output.close();work.close()
    for db,_,_ in sources:db.close()
    receipt=dict(**metadata,sha256=digest_file(output_path),bytes=output_path.stat().st_size,
        observations_sha256=digest_file(work_path),observations_bytes=work_path.stat().st_size,
        seconds=round(time.monotonic()-started,2),complete=True)
    (args.output/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    (args.output/'ATTRIBUTION.txt').write_text('\n'.join((path.parent/'ATTRIBUTION.txt').read_text() for path,_ in inputs)+
        'Retained example owners/source references are in references_used; source context artifact retains full provenance.\n'
        'Changes: counts of directly attested lexical correspondences and original nearby words. Experimental selection evidence.\n')
    print(canonical(receipt),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('contexts','output'):p.add_argument('--'+name,type=Path,required=True)
    for name in ('additional-context','additional-corpus-receipt','source-exclusions','release-adapter'):
        p.add_argument('--'+name,type=Path)
    p.add_argument('--base-supplement-receipt',type=Path,action='append',default=[])
    p.add_argument('--extra-context',type=Path,action='append',default=[])
    p.add_argument('--extra-corpus-receipt',type=Path,action='append',default=[])
    p.add_argument('--pair',action='append',required=True)
    p.add_argument('--minimum-support',type=int,default=3);p.add_argument('--minimum-agreement',type=float,default=.98)
    args=p.parse_args();assert args.minimum_support>=2 and .5<=args.minimum_agreement<=1
    if args.additional_context:assert args.additional_corpus_receipt and args.source_exclusions
    compile(args)
