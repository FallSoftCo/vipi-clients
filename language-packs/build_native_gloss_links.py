#!/usr/bin/env python3
"""Import explicit short native dictionary glosses as direct English links.

These remain separate sense identities, not fabricated English pivot senses.
They never authorize non-English pair inference or contextual sense selection.
"""
import argparse
from collections import Counter
from functools import lru_cache
from itertools import groupby
import json
from pathlib import Path
import re
import sqlite3
import time
from build_wiktextract import canonical,digest_file,EXCLUDED,PARTS,NON_ROMAN,readable_roman

GRAMMATICAL_TAGS={'transitive','intransitive','ditransitive','countable','uncountable',
    'singular','plural','masculine','feminine','neuter','animate','inanimate','perfective','imperfective'}

def counterparts(rows):
    leaves=set()
    for glosses,raw_tags,forms,alts in rows:
        tags=set(json.loads(raw_tags))
        if tags&EXCLUDED:continue
        # Register, region, gendered-person and field restrictions are not
        # guessed from a bare English counterpart. Preserve the original data
        # in the inventory; this direct-link supplement abstains.
        if tags-GRAMMATICAL_TAGS or json.loads(forms) or json.loads(alts):return None
        glosses=json.loads(glosses)
        if not glosses:return None
        leaves.add(glosses[-1])
    if len(leaves)!=1:return None
    leaf=next(iter(leaves));value=leaf.lower().rstrip('.')
    values=[re.sub(r'^to ','',part.strip()) for part in re.split('[,;]',value)]
    if any(not re.fullmatch(r"[a-z]+(?:[ '-][a-z]+)?",word) for word in values):return None
    return leaf,sorted(set(values))

def build(inventory,output):
    receipt=json.loads((inventory.parent/'receipt.json').read_text())
    assert receipt['native_scope']=='all-native-entries' and receipt['complete_source_scan'] and digest_file(inventory)==receipt['sha256']
    output.mkdir(parents=True,exist_ok=False);started=time.monotonic();counts=Counter();path=output/'gloss-links.sqlite'
    source=sqlite3.connect(inventory.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
    source.execute('PRAGMA temp_store=FILE')
    @lru_cache(maxsize=150000)
    def english(word,pos):
        matches=[]
        for identifier,tags in source.execute('''SELECT source_line,tags FROM native_entries
            WHERE language='en' AND normalized=? AND headword=? AND part_of_speech=?''',(word,word,pos)):
            if set(json.loads(tags))&EXCLUDED:continue
            leaf=False;alias=False
            for glosses,tags,forms,alts in source.execute('SELECT glosses,tags,form_of,alt_of FROM native_senses WHERE source_line=?',(identifier,)):
                if set(json.loads(tags))&EXCLUDED:continue
                if json.loads(forms) or json.loads(alts):alias=True
                elif json.loads(glosses):leaf=True
            if leaf and not alias:matches.append(identifier)
        return matches[0] if len(matches)==1 else None
    with sqlite3.connect(path) as db:
        db.executescript('''PRAGMA temp_store=FILE;
            CREATE TABLE links(language TEXT NOT NULL,native_line INTEGER NOT NULL,english_line INTEGER NOT NULL,
            headword TEXT NOT NULL,english_word TEXT NOT NULL,gloss TEXT NOT NULL,reading TEXT NOT NULL,
            source_url TEXT NOT NULL,PRIMARY KEY(language,native_line,english_line)) WITHOUT ROWID;
            CREATE INDEX english_links ON links(english_line);
            CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL) WITHOUT ROWID;''')
        records=source.execute('''SELECT e.source_line,e.language,e.headword,e.part_of_speech,e.tags,e.source_url,
            s.glosses,s.tags,s.form_of,s.alt_of FROM native_entries e JOIN native_senses s USING(source_line)
            WHERE e.language<>'en' AND e.part_of_speech IN ('noun','verb','adj','adv','intj')
            ORDER BY e.source_line,s.sense_index''')
        for identifier,group in groupby(records,key=lambda row:row[0]):
            rows=list(group);_,language,head,pos,tags,url,*_=rows[0]
            if set(json.loads(tags))&EXCLUDED:continue
            parsed=counterparts([r[6:] for r in rows])
            if not parsed:continue
            gloss,words=parsed;english_words=[(word,english(word,pos)) for word in words]
            english_words=[(w,i) for w,i in english_words if i]
            if not english_words:continue
            reading=''
            if language in NON_ROMAN:
                readings=set()
                for form,tags in source.execute('SELECT form,tags FROM native_forms WHERE source_line=?',(identifier,)):
                    tags=set(json.loads(tags))
                    if 'romanization' in tags and not tags&EXCLUDED:
                        value=readable_roman(form)
                        if value:readings.add(value)
                if len(readings)==1:reading=next(iter(readings))
            for word,target in english_words:
                db.execute('INSERT INTO links VALUES (?,?,?,?,?,?,?,?)',(language,identifier,target,head,word,gloss,reading,url));counts[language]+=1
            if sum(counts.values())%10000==0:db.commit()
        metadata=dict(schema='vipi-native-gloss-links-1',source_inventory_sha256=receipt['sha256'],
            upstream_sha256=receipt['upstream_sha256'],compiler_sha256=digest_file(Path(__file__)),
            quality='explicit-short-native-gloss-direct-English-link',license='CC-BY-SA-4.0',
            indirect_pair_inference=False,individually_reviewed=False)
        db.executemany('INSERT INTO metadata VALUES (?,?)',[(k,canonical(v)) for k,v in metadata.items()]);db.commit()
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    result=dict(**metadata,complete=True,counts=dict(counts),sha256=digest_file(path),bytes=path.stat().st_size,seconds=round(time.monotonic()-started,2))
    (output/'receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(canonical(result),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inventory',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();build(a.inventory,a.output)
