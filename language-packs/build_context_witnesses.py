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
    assert parent['complete'] and not parent['pilot'] and parent['schema']=='vipi-broad-lexical-contexts-2'
    assert digest_file(args.contexts)==parent['sha256']
    selected={tuple(pair.split('-')) for pair in args.pair}
    assert selected and all(len(pair)==2 and pair[0]!=pair[1] and all(x in parent['languages'] for x in pair) for pair in selected)
    source=sqlite3.connect(args.contexts.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
    source.execute('PRAGMA temp_store=FILE');source.execute('PRAGMA cache_size=-32768')
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
        language,text,owner=source.execute('SELECT language,text,owner FROM sentences WHERE id=?',(identifier,)).fetchone()
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
    for a,b,sa,se,ta,te in source.execute(query,arguments):
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
        source_contexts_sha256=parent['sha256'],source_release_id=parent['source_release_id'],
        minimum_support=args.minimum_support,minimum_agreement=args.minimum_agreement,
        counts=dict(counts),pairs=dict(by_pair),compiler_sha256=digest_file(Path(__file__)),
        independent_semantic_acceptance=False,release_ready=False,
        warning='Reference agreement is not a calibrated correctness probability. Dictionary sense IDs are not classifier labels.',
        cue_policy='up to six original ICU words on each side in the same clause, or whole lexical message',
        license='CC BY 2.0 FR; dictionary evidence provenance CC-BY-SA-4.0')
    output.executemany('INSERT INTO metadata VALUES (?,?)',[(k,canonical(v)) for k,v in metadata.items()]);output.commit()
    assert output.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    output.close();work.close();source.close()
    receipt=dict(**metadata,sha256=digest_file(output_path),bytes=output_path.stat().st_size,seconds=round(time.monotonic()-started,2),complete=True)
    (args.output/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    (args.output/'ATTRIBUTION.txt').write_text('Tatoeba contributors, CC BY 2.0 FR. Individual owners and sentence IDs in references_used.\n'
        'References: https://tatoeba.org/en/sentences/show/{sentence}. Dictionary-derived alignment evidence: Wiktionary contributors, CC BY-SA 4.0.\n'
        'Changes: counts of directly attested lexical correspondences and original nearby words. Experimental selection evidence.\n')
    print(canonical(receipt),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('contexts','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--pair',action='append',required=True)
    p.add_argument('--minimum-support',type=int,default=3);p.add_argument('--minimum-agreement',type=float,default=.98)
    args=p.parse_args();assert args.minimum_support>=2 and .5<=args.minimum_agreement<=1;compile(args)
