#!/usr/bin/env python3
"""Freeze source-only phrase queries; evaluation terms never reach translation."""
import hashlib
import json
from pathlib import Path

root=Path(__file__).resolve().parents[2]
prior=root/'artifacts/context-marker-protocol-001.json'
samples=json.loads(prior.read_text())['samples']
cases=[{**row,'evaluation_scope':'reused authored development correspondence'} for row in samples]
regression=root/'artifacts/packs/source-senses-pilot-001/regression.json'
for index,row in enumerate(json.loads(regression.read_text())['cases']):
    if row['rejected_source']!='lectura': continue
    source,target=row['pair'].split('-'); original=row['original']; word=row['rejected_source']
    start=original.index(word)
    cases.append({'source':source,'target':target,'original':original,'source_word':word,
        'start':len(original[:start].encode('utf-16-le'))//2,
        'end':len(original[:start+len(word)].encode('utf-16-le'))//2,
        'case':row['case'],'concept':'legislative_reading','evaluation_scope':'known regression; not held out'})
for source,target,original,focus,concept in [
    ('es','en','Papá está preparando la cena. ¿Puedes comprar pan de camino a casa?','de camino','recipient_route'),
    ('es','en','Compré pan de camino a casa.','de camino','speaker_route'),
    ('en','de','My sister works at a bank. She will help me open an account tomorrow.','help','assistance'),
    ('en','es','Can you bring my book?','book','speaker_possession'),
    ('en','es','Can you bring your book?','book','recipient_possession'),
    ('en','es','Can they bring their books?','books','plural_possession')]:
    start=original.index(focus)
    cases.append({'source':source,'target':target,'original':original,'source_word':focus,
        'start':len(original[:start].encode('utf-16-le'))//2,
        'end':len(original[:start+len(focus)].encode('utf-16-le'))//2,
        'case':'phrase_regression_'+concept,'concept':concept,
        'evaluation_scope':'authored development regression; not held out'})
protocol={'schema':'vipi-local-phrase-probe-1','scope':'Whole plus overlapping phrase translations; research only',
    'prior_protocol_sha256':hashlib.sha256(prior.read_bytes()).hexdigest(),
    'regression_sha256':hashlib.sha256(regression.read_bytes()).hexdigest(),
    'window_extents':[[0,0],[1,0],[0,1],[1,1],[2,0],[0,2],[2,2]],
    'maximum_phrase_characters':192,'maximum_window_words':8,
    'meaning_acceptance':False,'samples':cases}
path=root/'artifacts/phrase-protocol-001.json'
with path.open('x') as stream: json.dump(protocol,stream,ensure_ascii=False,indent=2); stream.write('\n')
print(json.dumps({'cases':len(cases),'pairs':len({(c['source'],c['target']) for c in cases}),
                  'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}))
