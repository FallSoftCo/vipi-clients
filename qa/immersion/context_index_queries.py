#!/usr/bin/env python3
"""Prepare cross-platform index portability queries, not semantic acceptance."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'language-packs'))
from context_hints import lookup_key

SQL = '''SELECT e.id,e.target FROM context_search JOIN examples e ON e.id=context_search.docid
 WHERE context_search MATCH ? AND e.source_language=? AND e.target_language=? AND e.source_key=?
 ORDER BY e.id LIMIT 8'''


def main(args):
    path = args.index / 'contexts.sqlite'
    receipt = json.loads((args.index / 'receipt.json').read_text())
    assert receipt['complete_source_scan'] and hashlib.sha256(path.read_bytes()).hexdigest() == receipt['sha256']
    grammar = json.loads(args.grammar_guard.read_text())['terms']
    cases = []
    with sqlite3.connect(path.resolve().as_uri() + '?mode=ro&immutable=1', uri=True) as db:
        pairs = db.execute('SELECT source_language,target_language,count(*) FROM examples GROUP BY 1,2 ORDER BY 1,2').fetchall()
        for source, target, count in pairs:
            for offset in sorted({0, count//2, count-1}):
                row = db.execute('SELECT id,source_key,source_context,search_text FROM examples WHERE source_language=? AND target_language=? ORDER BY id LIMIT 1 OFFSET ?', (source,target,offset)).fetchone()
                terms = re.findall(r'[^\W\d_]+', row[3], re.UNICODE)
                context_terms = list(dict.fromkeys(t for t in terms if lookup_key(t,source) not in grammar[source] and lookup_key(t,source) != row[1]))[:3]
                if not context_terms: context_terms = terms[:1]
                if not context_terms: continue
                query = ' OR '.join('"' + term.replace('"','""') + '"' for term in context_terms)
                expected = [{'id': result[0], 'target': result[1]} for result in db.execute(SQL, (query,source,target,row[1]))]
                assert expected
                cases.append({'source':source,'target':target,'source_key':row[1],'query':query,'context':row[2],'expected':expected})
    output = args.index / 'native-queries.json'; assert not output.exists()
    output.write_text(json.dumps({'purpose':'Attested-example self-retrieval and native SQLite portability, not semantic acceptance',
        'database_sha256':receipt['sha256'], 'database_bytes':receipt['bytes'], 'pairs':len(pairs), 'queries':cases}, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'queries':len(cases),'pairs':len(pairs),'linguistic_acceptance':False}))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index',type=Path,required=True)
    parser.add_argument('--grammar-guard',type=Path,required=True)
    main(parser.parse_args())
