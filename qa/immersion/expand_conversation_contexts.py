#!/usr/bin/env python3
"""Expand authored lexical seeds using direct development-only Tatoeba links.

Outputs are candidates requiring semantic assessment. A linked sentence pair
and two matching forms do not prove that the words have the seed's meaning.
No indirect translations, automatic approvals, or reserved examples are used.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import heapq
import json
from functools import lru_cache
from pathlib import Path
import re
import sqlite3
import sys
import icu
from conversation_corpus import key, sha_file, write_json
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'language-packs'))
from authored_conversation import records
from mapping_catalog import validate
from build_wiktextract import canonical


@lru_cache(maxsize=32)
def focus_pattern(words):
    return re.compile('|'.join(re.escape(word) for word in sorted(words,key=len,reverse=True)),re.IGNORECASE)


def focus_matches(text,language,forms):
    candidates=list(focus_pattern(tuple(sorted(forms))).finditer(text))
    if not candidates:return {}
    iterator=icu.BreakIterator.createWordInstance(icu.Locale(language))
    value=icu.UnicodeString(text);iterator.setText(value);positions={0,*list(iterator)}
    found=defaultdict(list)
    for match in candidates:
        start,end=match.span();word=match.group();normalized=key(word)
        if len(text[:start].encode('utf-16-le'))//2 not in positions or len(text[:end].encode('utf-16-le'))//2 not in positions:continue
        if normalized in forms:
            for concept,reading,meaning in forms[normalized]:
                found[concept].append((word,start,end,reading,meaning))
    # A repeated word supplies no unambiguous alignment within this sentence.
    return {concept:items[0] for concept,items in found.items() if len(items)==1}


def main(args):
    args.output.mkdir(parents=True,exist_ok=False)
    seed=defaultdict(lambda:defaultdict(set))
    for record in records():
        concept=record['logical_id'].split(':')[1]
        seed[record['target_language']][key(record['target'])].add((concept,record['reading'],record['meaning']))
    corpus=sqlite3.connect(args.corpus.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
    metadata=json.loads(corpus.execute("SELECT value FROM metadata WHERE key='receipt'").fetchone()[0])
    if metadata.get('tags_schema')!='tag_id,sentence_id,username,added_time':
        raise ValueError('Corrected publisher tag schema required')
    work=sqlite3.connect(args.output/'focus.sqlite');work.execute('PRAGMA temp_store=FILE')
    work.execute('CREATE TABLE focus(sentence INTEGER PRIMARY KEY,payload TEXT NOT NULL)')
    # Editorial flags are evidence of unresolved problems, regardless of
    # whether the problem is lexical, spelling, grammar, copyright or audio.
    flagged={row[0] for row in corpus.execute('''SELECT DISTINCT t.sentence FROM tags t JOIN tag_metadata m ON m.id=t.tag
      WHERE m.name LIKE '@%' OR lower(m.name) LIKE '%unnatural%' OR lower(m.name) LIKE '%incorrect%'
      OR lower(m.name) IN ('not natural','non natural','less than natural')''')}
    counts=Counter();batch=[]
    for identifier,language,text in corpus.execute("SELECT id,language,text FROM sentences WHERE partition='development' AND length(text) BETWEEN 5 AND 280"):
        counts['development_sentences_scanned']+=1
        if identifier in flagged: counts['flagged_sentences_excluded']+=1;continue
        matches=focus_matches(text,language,seed[language])
        if matches:batch.append((identifier,json.dumps(matches,ensure_ascii=False)));counts['sentences_with_seed_focus']+=1
        if len(batch)>=10000:
            work.executemany('INSERT INTO focus VALUES (?,?)',batch);work.commit();batch=[]
    work.executemany('INSERT INTO focus VALUES (?,?)',batch);work.commit()
    work.execute('ATTACH DATABASE ? AS corpus',(str(args.corpus.resolve()),))
    heaps=defaultdict(list);corpus_receipt_sha=sha_file(args.corpus.parent/'receipt.json')
    sql='''SELECT a.id,a.language,a.text,a.owner,fa.payload,b.id,b.language,b.text,b.owner,fb.payload
      FROM corpus.links l JOIN focus fa ON fa.sentence=l.a JOIN focus fb ON fb.sentence=l.b
      JOIN corpus.sentences a ON a.id=l.a JOIN corpus.sentences b ON b.id=l.b WHERE a.language!=b.language'''
    for aid,al,at,ao,af,bid,bl,bt,bo,bf in work.execute(sql):
        left,right=json.loads(af),json.loads(bf)
        for concept in left.keys() & right.keys():
            for sid,sl,st,so,sf,tid,tl,tt,to,tf in [(aid,al,at,ao,left[concept],bid,bl,bt,bo,right[concept]),
                                               (bid,bl,bt,bo,right[concept],aid,al,at,ao,left[concept])]:
                identity=f'tatoeba-direct:{sid}:{tid}:{concept}'
                digest=hashlib.sha256(identity.encode()).hexdigest();rank=int(digest,16)
                record={'schema':'vipi-contextual-mapping-1','logical_id':identity,
                    'source_language':sl,'target_language':tl,'source':sf[0],'target':tf[0],'reading':tf[3],
                    'source_context':st,'target_context':tt,'source_span':sf[1:3],'target_span':tf[1:3],
                    'meaning':'Candidate seed meaning requiring context review: '+sf[4],
                    'usage':{'scope':'lexical_focus_only','context_generalization':'none; candidate context only',
                        'alignment_evidence':'one occurrence of each seed form in directly linked sentences',
                        'source_boundary_evidence':'ICU '+icu.ICU_VERSION+' word boundaries; native parity not yet checked'},
                    'provenance':{'author':'Tatoeba contributors: '+(so if so!='\\N' else 'unowned')+'; '+(to if to!='\\N' else 'unowned'),
                        'license':'CC BY 2.0 FR','source_url':f'https://tatoeba.org/en/sentences/show/{sid}',
                        'target_url':f'https://tatoeba.org/en/sentences/show/{tid}',
                        'source_sentence_id':sid,'target_sentence_id':tid,'direct_link':True,
                        'corpus_receipt_sha256':corpus_receipt_sha,
                        'partition':'development','independent_acceptance_data':False}}
                try:validate(record)
                except ValueError:counts['schema_rejections']+=1;continue
                counts['eligible_direct_candidates']+=1
                group=(sl,tl,concept);heap=heaps[group]
                item=(-rank,identity,record)
                if len(heap)<args.per_group:heapq.heappush(heap,item)
                elif item[0]>heap[0][0]:heapq.heapreplace(heap,item)
    output=args.output/'records.jsonl';pair_counts=Counter()
    with output.open('x') as stream:
        for group in sorted(heaps):
            for _,identity,record in sorted(heaps[group],key=lambda x:x[1]):
                stream.write(canonical(record)+'\n');pair_counts[group[0]+'-'+group[1]]+=1
    corpus.close();work.close()
    result={'schema':'vipi-tatoeba-context-expansion-1','counts':dict(counts),'records':sum(pair_counts.values()),
        'pairs':dict(pair_counts),'per_concept_direction_cap':args.per_group,'selection':'lowest stable identity SHA256 ranks',
        'records_sha256':sha_file(output),'extractor_sha256':sha_file(Path(__file__)),
        'seed_sha256':sha_file(Path(__file__).resolve().parents[2]/'language-packs/authored_conversation.py'),
        'linguistic_acceptance':False,'runtime_integration':False,'reserved_partition_read':False}
    write_json(args.output/'receipt.json',result);print(json.dumps(result))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('corpus','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--per-group',type=int,default=20);args=p.parse_args()
    if not 1<=args.per_group<=1000:p.error('per-group must be 1..1000')
    main(args)
