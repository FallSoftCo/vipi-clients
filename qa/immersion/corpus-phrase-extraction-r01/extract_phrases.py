#!/usr/bin/env python3
"""Consistent phrase spans with every permitted unaligned boundary variant."""
import collections
import gzip
import hashlib
import json
import math
import sqlite3
import time
from pathlib import Path
from extract_pgv import OUT, HERE, sha, guards, process_hwm
from prepare_inputs import norm

STOPS = {'.', '!', '?', '。', '！', '？'}


def crosses_stop(tokens):
    return any(t in STOPS for t in tokens[:-1])


def consistent_targets(source_start, source_end, target_tokens, links, maximum=12):
    """Return target half-open spans and minimal span; an empty alignment abstains.

    A target interval may not connect outside this source interval. Any number
    of adjacent unaligned target words may expand its boundaries within caps.
    This structural property is NOT evidence that the phrase is complete/correct.
    """
    connected = [t for s, t in links if source_start <= s < source_end]
    if not connected:
        return []
    lo, hi = min(connected), max(connected)+1
    if hi-lo > maximum or crosses_stop(target_tokens[lo:hi]):
        return []
    if any(lo <= t < hi and not source_start <= s < source_end for s, t in links):
        return []
    aligned_targets = {t for _, t in links}
    lefts, rights = [lo], [hi]
    while lefts[-1] > 0 and lefts[-1]-1 not in aligned_targets:
        candidate = lefts[-1]-1
        if crosses_stop(target_tokens[candidate:hi]):
            break
        lefts.append(candidate)
    while rights[-1] < len(target_tokens) and rights[-1] not in aligned_targets:
        candidate = rights[-1]+1
        if crosses_stop(target_tokens[lo:candidate]):
            break
        rights.append(candidate)
    return [(a,b,lo,hi) for a in lefts for b in rights
            if b-a <= maximum and not crosses_stop(target_tokens[a:b])]


def parse_links(line, source_count, target_count):
    result = {tuple(map(int, item.split('-'))) for item in line.split()}
    assert all(0 <= s < source_count and 0 <= t < target_count for s,t in result)
    return result


def parameters(path):
    result = {}
    with path.open() as f:
        for line in f:
            condition,prediction,prob = line.rstrip('\n').split('\t')
            result[(condition,prediction)] = float(prob)
    return result


def lexical_score(source, target, links, forward, reverse):
    # Mean log of the per-word average conditional probability, both directions.
    # Missing exported entries use explicit1e-12floor; retain missing counts.
    # This is a diagnostic tie score, never a calibrated correctness estimate.
    scores, missing = [], 0
    for predicted, conditioned, points, table in [(target,source,links,forward), (source,target,{(t,s) for s,t in links},reverse)]:
        total = 0.0
        for j, token in enumerate(predicted):
            contexts = [conditioned[i] for i,k in points if k == j] or ['<eps>']
            values = []
            for context in contexts:
                value = table.get((context,token))
                if value is None:
                    missing += 1
                    value = math.log(1e-12)
                values.append(math.exp(value))
            total += math.log(sum(values)/len(values))
        scores.append(total/len(predicted))
    return sum(scores)/2, missing


def main():
    start = time.monotonic()
    freeze = json.loads((OUT/'input-freeze.json').read_text())
    assert sha(OUT/'source-frequency-keys.json') == freeze['source_frequency_sha256']
    aligned = json.loads((OUT/'alignments/receipt.json').read_text())
    assert aligned['complete']
    frequency = json.loads((OUT/'source-frequency-keys.json').read_text())
    keys = {r['source_key']:r for r in frequency['unigram_keys']+frequency['multiword_keys']}
    destination = OUT/'phrases'
    destination.mkdir(exist_ok=False)
    execution = dict(production=False, extractor_sha256=sha(Path(__file__)), protocol_sha256=freeze['protocol_sha256'], source_frequency_sha256=freeze['source_frequency_sha256'], alignment_receipt_sha256=sha(OUT/'alignments/receipt.json'), score='Mean across directions of per-word mean log average conditional lexical probability; missing exported values floor1e-12 explicitly counted. Distinct components rank first; all alternatives retained.', target_stop_policy='A terminal sentence stop may be included at the end; no token after a stop is included.', maximum_source_tokens=8, maximum_target_tokens=12)
    (destination/'execution-freeze.json').write_text(json.dumps(execution,indent=2)+'\n')
    db = sqlite3.connect(destination/'candidates.sqlite')
    db.executescript('''PRAGMA temp_store=FILE; PRAGMA cache_size=-32768;
      CREATE TABLE variants(id TEXT PRIMARY KEY,pair TEXT,arm TEXT,source_key TEXT,target_key TEXT,
      source_tokens INTEGER,target_tokens INTEGER,observations INTEGER,lexical_score_sum REAL,
      missing_lexical_parameters INTEGER,expanded_observations INTEGER,example_pair_index INTEGER,
      source_start INTEGER,source_end INTEGER,target_start INTEGER,target_end INTEGER) WITHOUT ROWID;
      CREATE TABLE components(variant TEXT,component INTEGER,PRIMARY KEY(variant,component)) WITHOUT ROWID;
      CREATE INDEX source_lookup ON variants(pair,arm,source_key);''')
    receipt = dict(complete=False, production=False, pairs=[])
    try:
        for pair in ['en-sw','en-es']:
            forward = parameters(OUT/f'alignments/{pair}-forward.params')
            reverse = parameters(OUT/f'alignments/{pair}-reverse.params')
            counts = collections.Counter()
            handles = {name:(OUT/f'alignments/{pair}-{name}.align').open() for name in ['forward','reverse','intersect','grow-diag-final-and']}
            with gzip.open(OUT/f'{pair}-pairs.jsonl.gz','rt') as rows, gzip.open(destination/f'{pair}-observations.jsonl.gz','xt',encoding='utf-8') as obs:
                for raw in rows:
                    row = json.loads(raw)
                    st, tt = row['source']['tokens'], row['target']['tokens']
                    sw, tw = [t['text'].casefold() for t in st], [t['text'].casefold() for t in tt]
                    all_links = {name:parse_links(next(handle),len(st),len(tt)) for name,handle in handles.items()}
                    def record(arm,ss,se,ts,te,lo,hi,links):
                        source_key = norm(row['source']['text'][st[ss]['codepoints'][0]:st[se-1]['codepoints'][1]])
                        target_raw = row['target']['text'][tt[ts]['codepoints'][0]:tt[te-1]['codepoints'][1]]
                        target_key = norm(target_raw)
                        identity = hashlib.sha256(json.dumps([pair,arm,source_key,target_key],ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
                        local = {(s-ss,t-ts) for s,t in links if ss <= s < se and ts <= t < te}
                        score, missing = lexical_score(sw[ss:se],tw[ts:te],local,forward,reverse)
                        expanded = int((ts,te)!=(lo,hi))
                        db.execute('''INSERT INTO variants VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                          ON CONFLICT(id) DO UPDATE SET observations=observations+1,
                          lexical_score_sum=lexical_score_sum+excluded.lexical_score_sum,
                          missing_lexical_parameters=missing_lexical_parameters+excluded.missing_lexical_parameters,
                          expanded_observations=expanded_observations+excluded.expanded_observations''',
                          (identity,pair,arm,source_key,target_key,se-ss,te-ts,1,score,missing,expanded,row['index'],ss,se,ts,te))
                        assert row['source']['component'] == row['target']['component']
                        db.execute('INSERT OR IGNORE INTO components VALUES(?,?)',(identity,row['source']['component']))
                        observation=dict(variant_id=identity,pair_index=row['index'],pair_id=row['pair_id'],arm=arm,
                                         source_tokens=[ss,se],target_tokens=[ts,te],minimal_target_tokens=[lo,hi],
                                         source_codepoints=[st[ss]['codepoints'][0],st[se-1]['codepoints'][1]],
                                         source_utf16=[st[ss]['utf16'][0],st[se-1]['utf16'][1]],
                                         target_codepoints=[tt[ts]['codepoints'][0],tt[te-1]['codepoints'][1]],
                                         target_utf16=[tt[ts]['utf16'][0],tt[te-1]['utf16'][1]],
                                         links=sorted(local),lexical_score=score,missing_lexical_parameters=missing)
                        obs.write(json.dumps(observation,separators=(',',':'))+'\n')
                        counts[arm+':observations'] += 1
                        counts[arm+':expanded_observations'] += expanded
                    mutual = all_links['forward'] & all_links['reverse']
                    degrees_s, degrees_t = collections.Counter(s for s,t in mutual),collections.Counter(t for s,t in mutual)
                    for ss,ts in sorted(mutual):
                        if degrees_s[ss]==degrees_t[ts]==1 and norm(st[ss]['text']) in keys:
                            record('mutual-word',ss,ss+1,ts,ts+1,ts,ts+1,mutual)
                    for ss in range(len(st)):
                        for se in range(ss+1,min(len(st),ss+8)+1):
                            if crosses_stop(sw[ss:se]):
                                break
                            key = norm(row['source']['text'][st[ss]['codepoints'][0]:st[se-1]['codepoints'][1]])
                            if key not in keys:
                                continue
                            counts['source_inventory_occurrences'] += 1
                            for arm in ['intersect','grow-diag-final-and']:
                                for ts,te,lo,hi in consistent_targets(ss,se,tw,all_links[arm]):
                                    record(arm,ss,se,ts,te,lo,hi,all_links[arm])
                    counts['sentence_pairs'] += 1
                    if counts['sentence_pairs']%250==0:
                        db.commit()
                        guards(start,1800)
                        if counts['sentence_pairs']%2500==0:
                            print(json.dumps(dict(pair=pair,counts=dict(counts),seconds=time.monotonic()-start)),flush=True)
                assert all(handle.readline()=='' for handle in handles.values())
            for handle in handles.values():
                handle.close()
            db.commit()
            receipt['pairs'].append(dict(pair=pair,counts=dict(counts)))
            del forward,reverse
        db.execute('''CREATE TABLE ranked AS SELECT v.*,count(c.component) AS distinct_components,
          v.lexical_score_sum/v.observations AS mean_lexical_score FROM variants v
          JOIN components c ON c.variant=v.id GROUP BY v.id''')
        db.execute('CREATE INDEX ranked_lookup ON ranked(pair,arm,source_key,distinct_components DESC,mean_lexical_score DESC,id)')
        db.commit()
        receipt['complete'] = True
    except BaseException as exc:
        receipt['error'] = repr(exc)
        raise
    finally:
        db.close()
        receipt.update(seconds=time.monotonic()-start,process_vm_hwm_bytes=process_hwm(),outputs={p.name:dict(bytes=p.stat().st_size,sha256=sha(p)) for p in destination.glob('*') if p.is_file() and p.name!='receipt.json'})
        (destination/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')


if __name__ == '__main__':
    main()
