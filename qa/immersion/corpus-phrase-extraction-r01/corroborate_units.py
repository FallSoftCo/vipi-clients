#!/usr/bin/env python3
"""Attach complete dictionary-unit identities; never infer contextual approval."""
import collections
import functools
import json
import sqlite3
import time
from pathlib import Path
from extract_pgv import OUT, HERE, sha, guards, process_hwm
from prepare_inputs import norm


def complete_units(db, key):
    # surfaces has a keyed normalized index; lexemes.normalized is NOT indexed.
    # Avoid a full lexical scan for every phrase and do not mutate bundled DBs.
    result = []
    rows = db.execute('''SELECT f.lexeme,f.surface,f.start,f.end,f.number,f.mode,f.features,
      l.headword,l.pos,l.source_safe,l.target_safe,l.source_url
      FROM surfaces f JOIN lexemes l ON l.id=f.lexeme WHERE f.normalized=?''',(key,))
    for lexeme,surface,start,end,number,mode,features,headword,pos,source_safe,target_safe,url in rows:
        if start != 0 or end != len(surface.encode('utf-16-le'))//2 or norm(surface) != key:
            continue
        terms = [dict(sense_id=sid,reading=reading,eligible=bool(eligible),qualifiers=json.loads(qualifiers),label=label,explicit=bool(explicit),sense_source_url=surl)
                 for sid,reading,eligible,qualifiers,label,explicit,surl in db.execute('''SELECT t.sense,t.reading,t.eligible,t.qualifiers,s.label,s.explicit,s.source_url
                   FROM terms t JOIN senses s ON s.id=t.sense WHERE t.lexeme=?''',(lexeme,))]
        result.append(dict(lexeme_id=lexeme,headword=headword,pos=pos,surface=surface,source_range=[start,end],number=number,mode=mode,features=json.loads(features),source_safe=bool(source_safe),target_safe=bool(target_safe),source_url=url,terms=terms))
    return result


def main():
    started = time.monotonic()
    protocol = json.loads((HERE/'protocol.json').read_text())
    phrase_path = OUT/'phrases/candidates.sqlite'
    phrase_receipt = json.loads((OUT/'phrases/receipt.json').read_text())
    assert phrase_receipt['complete']
    assert sha(phrase_path) == phrase_receipt['outputs']['candidates.sqlite']['sha256']
    source = sqlite3.connect(phrase_path.as_uri()+'?mode=ro&immutable=1',uri=True)
    dictionaries = {}
    identities = protocol['sources']['dictionary_assets']['expanded_db_hashes']
    for name,digest in identities.items():
        path=Path(name)
        assert sha(path)==digest
        dictionaries[path.stem[2:]]=sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True)
    output=OUT/'phrases/dictionary-units.sqlite'
    assert not output.exists()
    db=sqlite3.connect(output)
    db.executescript('''PRAGMA temp_store=FILE; PRAGMA cache_size=-32768;
      CREATE TABLE units(language TEXT,key TEXT,evidence TEXT,PRIMARY KEY(language,key)) WITHOUT ROWID;
      CREATE TABLE corroboration(variant TEXT PRIMARY KEY,source_complete_units INTEGER,
       target_complete_units INTEGER,shared_sense_ids TEXT,status TEXT) WITHOUT ROWID;''')
    @functools.lru_cache(maxsize=20000)
    def units(language,key):
        rows=complete_units(dictionaries[language],key)
        db.execute('INSERT OR IGNORE INTO units VALUES(?,?,?)',(language,key,json.dumps(rows,ensure_ascii=False,separators=(',',':'))))
        return rows
    counts=collections.Counter()
    for index,(vid,pair,source_key,target_key) in enumerate(source.execute('SELECT id,pair,source_key,target_key FROM variants')):
        sl,tl=pair.split('-')
        left,right=units(sl,source_key),units(tl,target_key)
        ls={t['sense_id'] for r in left for t in r['terms']}
        rs={t['sense_id'] for r in right for t in r['terms']}
        shared=sorted(ls & rs)
        status='shared_complete_dictionary_sense' if shared else ('both_complete_units_no_shared_sense' if left and right else 'one_or_both_complete_units_missing')
        db.execute('INSERT INTO corroboration VALUES(?,?,?,?,?)',(vid,len(left),len(right),json.dumps(shared),status))
        counts[status]+=1
        if index%500==0:
            db.commit()
            guards(started,1800)
    db.commit();db.close();source.close()
    for connection in dictionaries.values():connection.close()
    receipt=dict(complete=True,production=False,compiler_sha256=sha(Path(__file__)),candidate_db_sha256=sha(phrase_path),dictionary_hashes=identities,license='Dictionary evidence CC-BY-SA-4.0 retained independently of PGV CC-BY-4.0.',counts=dict(counts),meaning='Complete spelling/form and shared source sense identity are corroboration, not disambiguation of a new context. All lexical alternatives and eligible flags retained; ineligible/obscure/native-gloss links are not upgraded.',seconds=time.monotonic()-started,process_vm_hwm_bytes=process_hwm(),output_sha256=sha(output),output_bytes=output.stat().st_size)
    (OUT/'phrases/dictionary-units-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))


if __name__=='__main__':main()
