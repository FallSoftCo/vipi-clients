#!/usr/bin/env python3
"""Package assessed development frames as app-bundled public language assets.

App signing authenticates bundled assets; qualification keys are never shipped.
This does not promote development data or bypass later downloadable-pack trust.
"""
import argparse
import json
import shutil
import sqlite3
from pathlib import Path
from build_wiktextract import canonical, digest_file

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--input', type=Path, required=True)
p.add_argument('--contexts', type=Path)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
build = json.loads((a.input/'receipt.json').read_text())
if build['schema'] != 'vipi-reviewed-frame-build-1': raise ValueError('Wrong pack kind')
a.output.mkdir(parents=True, exist_ok=False)
packs = []
grouped_references = {}
def collect_references(path, identity):
    with sqlite3.connect(path) as db:
        for (evidence,) in db.execute('SELECT evidence FROM mappings ORDER BY id'):
            record = json.loads(evidence)['record']
            grouped_references.setdefault((identity, record['source_context']), set()).add(record['target_context'])
for pair in build['pairs']:
    identity = pair['pack_id']
    if identity != pair['source_language']+'-'+pair['target_language']: raise ValueError('Wrong pair')
    path = a.input/identity/'frames.sqlite'
    if digest_file(path) != pair['sha256']: raise ValueError('Changed database')
    shutil.copyfile(path, a.output/(identity+'.sqlite'))
    packs.append({'id':identity, 'sha256':pair['sha256'], 'bytes':pair['bytes']})
    # Only exact complete sentences receive an authored whole translation.
    # Never transfer their grammar to a different person's/tense's message.
    collect_references(path, identity)
contexts = []
if a.contexts:
    context_build = json.loads((a.contexts/'receipt.json').read_text())
    if context_build['schema'] != 'vipi-reviewed-context-build-1': raise ValueError('Wrong context pack kind')
    for pair in context_build['pairs']:
        identity = pair['pack_id']
        if identity != pair['source_language']+'-'+pair['target_language']: raise ValueError('Wrong context pair')
        path = a.contexts/identity/'contexts.sqlite'
        if digest_file(path) != pair['sha256'] or path.stat().st_size != pair['bytes']: raise ValueError('Changed context database')
        shutil.copyfile(path, a.output/(identity+'-contexts.sqlite'))
        contexts.append({'id':identity, 'sha256':pair['sha256'], 'bytes':pair['bytes']})
        collect_references(path, identity)
references = [{'pair':identity, 'original':original, 'translation':next(iter(targets))}
    for (identity,original),targets in sorted(grouped_references.items()) if len(targets)==1]
(a.output/'catalog.json').write_text(canonical({'schema':'vipi-bundled-frames-1', 'revision':2,
    'release_ready':False, 'build_sha256':digest_file(a.input/'receipt.json'),
    'context_build_sha256':digest_file(a.contexts/'receipt.json') if a.contexts else None,
    'packs':packs, 'contexts':contexts, 'references':references})+'\n')
(a.output/'NOTICE.txt').write_text('FallSoft.Co project-authored language constructions.\n'
    'Development data with explicit author assessment, not independent linguistic acceptance.\n'
    'Record provenance and assessments are retained in each database.\n')
print(canonical({'pairs':len(packs), 'context_pairs':len(contexts), 'references':len(references),
    'conflicting_references_omitted':sum(len(values)>1 for values in grouped_references.values()),
    'bytes':sum(p['bytes'] for p in packs+contexts), 'release_ready':False}))
