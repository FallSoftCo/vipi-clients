#!/usr/bin/env python3
"""Source-only contextual retrieval research; never accepted substitutions.

Queries use native source boundaries and nearby source text. Target references
and provider translations are retained only for review, never query construction.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import struct
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'language-packs'))
from context_hints import lookup_key, GRAMMAR
from build_context_examples import search_text

PROTECTED = re.compile(r'https?://\S+|www\.\S+|[\w.+-]+@[\w.-]+\.\w+|```[\s\S]*?(?:```|$)|`[^`]*(?:`|$)|[@#]\w+|\d+(?:[.,:]\d+)*')
SQL = '''SELECT e.id,e.target,e.reading,e.source_context,e.target_context,e.gloss,e.tags,
 matchinfo(context_search,'pcx') FROM context_search JOIN examples e ON e.id=context_search.docid
 WHERE context_search MATCH ? AND e.source_language=? AND e.target_language=? AND e.source_key=? LIMIT 129'''


def rank(blob, total):
    values = struct.unpack('=' + 'I'*(len(blob)//4), blob)
    phrases, columns = values[:2]; score = 0.; matches = 0
    assert columns == 1 and len(values) == 2 + phrases*columns*3
    for term in range(phrases):
        hits, _, documents = values[2+term*3:5+term*3]
        if hits:
            score += 1 + math.log((total+1)/(documents+1)); matches += 1
    return score, matches


def main(args):
    args.output.mkdir(exist_ok=False)
    index = args.index / 'contexts.sqlite'; receipt = json.loads((args.index/'receipt.json').read_text())
    assert hashlib.sha256(index.read_bytes()).hexdigest() == receipt['sha256']
    native = json.loads(args.candidates.read_text()); grammar = json.loads(args.grammar_guard.read_text())['terms']
    counts = Counter(); rows = []; start = time.monotonic(); missing = []
    with sqlite3.connect(index.resolve().as_uri()+'?mode=ro&immutable=1',uri=True) as db:
        total = db.execute('SELECT count(*) FROM examples').fetchone()[0]
        for pair in native['results']:
            source, target = pair['source'], pair['target']; pair_id = source+'-'+target
            keys = {x[0] for x in db.execute('SELECT DISTINCT source_key FROM examples WHERE source_language=? AND target_language=?',(source,target))}
            if not keys: missing.append(pair_id); continue
            for sample in pair['samples']:
                original = sample['original']; raw = original.encode('utf-16-le')
                protected = list(PROTECTED.finditer(original)); masked = list(original)
                for span in protected: masked[span.start():span.end()] = ' '*(span.end()-span.start())
                masked = ''.join(masked); found = []
                words = sample['source_words']
                for position in range(len(words)):
                    for length in range(1,min(5,len(words)-position)+1):
                        group = words[position:position+length]
                        if any(raw[a['end']*2:b['start']*2].decode('utf-16-le').strip() for a,b in zip(group,group[1:])): continue
                        lower, upper = group[0]['start'], group[-1]['end']
                        value = raw[lower*2:upper*2].decode('utf-16-le'); key = lookup_key(value,source)
                        if key not in keys: continue
                        char_start = len(raw[:lower*2].decode('utf-16-le')); char_end = char_start+len(value)
                        if any(span.start()<char_end and span.end()>char_start for span in protected): continue
                        stops = list(re.finditer(r'[.!?。！？\n]',masked))
                        left = max((m.end() for m in stops if m.end()<=char_start),default=0)
                        right = min((m.start() for m in stops if m.start()>=char_end),default=len(masked))
                        context = masked[left:char_start] + ' ' + masked[char_end:right]
                        terms = re.findall(r"[^\W\d_]+(?:['’-][^\W\d_]+)*", search_text(context,source), re.UNICODE)
                        terms = list(dict.fromkeys(t for t in terms if t not in grammar[source] and t not in GRAMMAR[source]))[:32]
                        if not terms: continue
                        query = ' OR '.join('"'+t.replace('"','""')+'"' for t in terms)
                        hits = db.execute(SQL,(query,source,target,key)).fetchall()
                        counts['lookups'] += 1
                        if len(hits)>128:
                            counts['bounded_candidate_overflow'] += 1; continue
                        ranked = []
                        for identifier, surface, reading, example, translated, gloss, tags, info in hits:
                            score, matches = rank(info,total)
                            ranked.append({'record':identifier,'target':surface,'reading':reading,'score':score,'matched_context_terms':matches,
                                           'example':example,'translated_example':translated,'gloss':gloss,'tags':json.loads(tags)})
                        ranked.sort(key=lambda row:(-row['score'],row['record']))
                        alternatives=[]; seen=set()
                        for row in ranked:
                            identity=(lookup_key(row['target'],target),row['gloss'])
                            if identity not in seen: alternatives.append(row); seen.add(identity)
                            if len(alternatives)==3: break
                        if alternatives:
                            found.append({'original':value,'start':lower,'end':upper,'query':query,'candidates':alternatives})
                counts['samples'] += 1; counts['with_retrievals'] += bool(found); counts['source_spans_with_retrievals'] += len(found)
                rows.append({'pair':pair_id,'case':sample['id'],'original':original,'reference':sample.get('reference'),
                             'provider_translation':sample['translation'],'retrievals':found})
    report={'policy':'source-only-fts4-context-retrieval-1','runtime_integration':False,'accepted_substitutions':False,'linguistic_acceptance':False,
            'index_sha256':receipt['sha256'],'capture_sha256':hashlib.sha256(args.candidates.read_bytes()).hexdigest(),
            'compiler_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'seconds':time.monotonic()-start,
            'limits':['Source-boundary reuse from regression capture, not fresh native execution.',
                      'Ranking uses lexical relevance, not a calibrated meaning probability.',
                      'No density selection, inflection/POS acceptance or phrase-scope acceptance.',
                      'Missing readings remain missing; targets never become display-ready from search alone.'],
            **counts,'missing_index_pairs':missing,'results':rows}
    if 'attribution' in native: report['attribution']=native['attribution']
    (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({**counts,'missing_index_pairs':len(missing),'seconds':report['seconds'],'linguistic_acceptance':False}))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index',type=Path,required=True)
    parser.add_argument('--candidates',type=Path,required=True)
    parser.add_argument('--grammar-guard',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    main(parser.parse_args())
