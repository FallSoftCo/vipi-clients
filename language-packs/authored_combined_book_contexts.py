#!/usr/bin/env python3
"""Combine the two explicitly assessed book carriers on opposite sides.

Only Chinese 看书 and the previously enumerated Korean 책 particles qualify.
No runtime morphology, new meaning, whole reference or corpus example is added.
"""
import argparse
import copy
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from authored_everyday import mapping
from build_wiktextract import canonical, digest_file
from mapping_catalog import digest, validate

BASELINE_SHA = '2a39428146be4d8c0463e1f0df72b2fe84d2b09861c78b0e5904ec4b7c84dd53'
KO_PARTS = [{'focus':'책'}, {'slot':['은','이','을','과','도','만','에','에서','의']}]
ZH_PARTS = [{'literal':'看'}, {'focus':'书'}]

def records(directory):
    assert digest_file(directory/'catalog.json') == BASELINE_SHA
    catalog = json.loads((directory/'catalog.json').read_text())
    for source,target in [('ko','zh'),('zh','ko')]:
        pair=source+'-'+target
        metadata=next(p for p in catalog['packs'] if p['id']==pair)
        path=directory/(pair+'.sqlite')
        assert path.stat().st_size==metadata['bytes'] and digest_file(path)==metadata['sha256']
        carriers={}
        with closing(sqlite3.connect('file:'+str(path.resolve())+'?mode=ro',uri=True)) as db:
            for payload,evidence in db.execute('SELECT payload,evidence FROM mappings ORDER BY id'):
                old=json.loads(payload)
                if old['source']!=('책' if source=='ko' else '书') or old['target']!=('책' if target=='ko' else '书'):continue
                for side,language in [('source',source),('target',target)]:
                    expected=KO_PARTS if language=='ko' else ZH_PARTS
                    if old[side+'_parts']==expected and old[side+'_lexical_unit'] is False:
                        assert digest(json.loads(evidence)['record'])==old['record_sha256']
                        assert language not in carriers
                        carriers[language]=old
        assert set(carriers)=={'ko','zh'}
        assert carriers['ko']['meaning']==carriers['zh']['meaning']
        assert carriers['ko']['reading']==carriers['zh']['reading']
        old=carriers['ko']; contexts=['책은' if language=='ko' else '看书' for language in (source,target)]
        row=mapping('combined_book_contexts',source,target,old['source'],old['target'],*contexts,old['meaning'],old['reading'])
        row['usage'].update(context_extent='local_phrase',lexical_unit=False,whole_reference=False,
            source_lexical_unit=False,target_lexical_unit=False,
            context_generalization='Explicit simultaneous Chinese reading construction and finite Korean noun particle',
            permitted_context='Unique literal book noun in both complete, enumerated carriers; sentence grammar stays outside focus',
            abstain_when=['Unlisted Korean ending, larger Chinese word, repeated carrier or missing corresponding book noun.',
                'Competing meaning, conflicting reading or protected identifier.'])
        for side,language,context in zip(('source','target'),(source,target),contexts,strict=True):
            row['usage'][side+'_frame_span']=[0,len(context)]
            row['usage'][side+'_frame_pattern']=copy.deepcopy(KO_PARTS if language=='ko' else ZH_PARTS)
        row['provenance'].update(baseline_catalog_sha256=BASELINE_SHA,
            baseline_carriers={language:{'id':value['id'],'record_sha256':value['record_sha256']} for language,value in carriers.items()},
            context_source='Exact previously assessed Chinese and Korean carriers, combined across the two sides',
            priority_basis='Native parity on existing authored references; no reserved message text',
            whole_reference_eligibility='False: neither carrier is a complete message translation')
        validate(row);yield row

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();rows=list(records(args.baseline));assert len(rows)==2
    args.output.mkdir(parents=True,exist_ok=False)
    path=args.output/'records.jsonl';path.write_text(''.join(canonical(row)+'\n' for row in rows))
    print(canonical(dict(records=len(rows),records_sha256=digest_file(path),authoring_source_sha256=digest_file(Path(__file__)),author_assessment_pending=True,release_ready=False)))
