#!/usr/bin/env python3
"""Explicit book focus in 看书, independently of native token segmentation.

Reuses exact assessed book forms/readings from bundle 019. No generic Chinese
compound splitting, tokenizer relaxation, or evaluation-text promotion.
"""
import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from authored_everyday import mapping
from authored_everyday_units import MEANINGS
from build_wiktextract import canonical,digest_file
from mapping_catalog import digest,validate

BASELINE_SHA='3682054944789de9b42dfac437e4027778607978880e75b091468411bce7d792'

def records(directory):
    if digest_file(directory/'catalog.json')!=BASELINE_SHA:raise ValueError('Changed baseline catalog')
    catalog=json.loads((directory/'catalog.json').read_text());seen={}
    for pack in catalog['packs']:
        if 'zh' not in pack['id'].split('-'):continue
        path=directory/(pack['id']+'.sqlite')
        if path.stat().st_size!=pack['bytes'] or digest_file(path)!=pack['sha256']:raise ValueError('Changed native pack')
        with closing(sqlite3.connect('file:'+str(path.resolve())+'?mode=ro',uri=True)) as db:
            for payload,evidence in db.execute('SELECT payload,evidence FROM mappings ORDER BY id'):
                old=json.loads(payload)
                if old.get('lexical_unit') is not True or old['meaning']!=MEANINGS['reading_book']:continue
                if any(old[side+'_language']=='zh' and old[side]!='书' for side in ('source','target')):continue
                if digest(json.loads(evidence)['record'])!=old['record_sha256']:raise ValueError('Changed source evidence')
                key=tuple(old[k] for k in ('source_language','target_language','source','target','meaning'))
                if key in seen and seen[key]['reading']!=old['reading']:raise ValueError('Conflicting reading')
                seen.setdefault(key,old)
    for key,old in sorted(seen.items()):
        source,target,left,right,meaning=key
        contexts=[('看' if language=='zh' else '')+word for language,word in [(source,left),(target,right)]]
        row=mapping('chinese_reading_focus_'+digest(key)[:32],source,target,left,right,*contexts,meaning,old['reading'])
        row['usage'].update(context_extent='local_phrase',lexical_unit=False,whole_reference=False,
            source_lexical_unit=source!='zh',target_lexical_unit=target!='zh',
            context_generalization='explicit 看书 construction with only 书 as the book focus',
            permitted_context='Literal reading of a book; complete unique 看书 and the exact corresponding assessed book noun must both occur',
            abstain_when=['看书 is absent, repeated, or only an internal fragment of a larger unapproved native form.',
                'The actual translation has no corresponding book noun, or meanings/readings compete.',
                'A protected identifier overlaps the focus.'])
        for side,language,word,context in zip(('source','target'),(source,target),(left,right),contexts,strict=True):
            row['usage'][side+'_frame_span']=[0,len(context)]
            row['usage'][side+'_frame_pattern']=([{'literal':'看'}] if language=='zh' else [])+[{'focus':word}]
        row['provenance'].update(baseline_catalog_sha256=BASELINE_SHA,baseline_record_sha256=old['record_sha256'],
            baseline_mapping_id=old['id'],lexical_source='Exact existing assessed book form, meaning and reading',
            context_source='Explicit authored 看书 construction; 看 stays outside the vocabulary focus',
            priority_basis='Native parity diagnostic on existing authored references, not reserved conversation text',
            whole_reference_eligibility='False: this construction cannot authorize a complete message translation')
        validate(row);yield row

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();rows=list(records(args.baseline));assert len(rows)==len({r['logical_id'] for r in rows})
    args.output.mkdir(parents=True,exist_ok=False);p=args.output/'records.jsonl';p.write_text(''.join(canonical(r)+'\n' for r in rows))
    print(canonical(dict(records=len(rows),pairs=len({(r['source_language'],r['target_language']) for r in rows}),
        records_sha256=digest_file(p),authoring_source_sha256=digest_file(Path(__file__)),author_assessment_pending=True,release_ready=False)))
