#!/usr/bin/env python3
"""Verify new attachment evidence, every finite index, and old record retention."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'language-packs'))
from build_wiktextract import digest_file
from export_reviewed_frames import compile_record


def audit(baseline, current, authored):
    before=json.loads((baseline/'catalog.json').read_text())
    after=json.loads((current/'catalog.json').read_text())
    expected={json.loads(line)['logical_id'] for line in authored.read_text().splitlines()}
    found=set();cases=0;directions=set();old_count=0
    for entry in after['packs']:
        identity=entry['id'];path=current/(identity+'.sqlite')
        assert digest_file(path)==entry['sha256'] and path.stat().st_size==entry['bytes']
        with sqlite3.connect('file:'+str(path.resolve())+'?mode=ro',uri=True) as db:
            assert db.execute('PRAGMA user_version').fetchone()[0]==8
            with sqlite3.connect('file:'+str((baseline/(identity+'.sqlite')).resolve())+'?mode=ro',uri=True) as old:
                previous={key:json.loads(payload)['record_sha256'] for key,payload in old.execute('SELECT id,payload FROM mappings')}
            retained={}
            for key,payload,evidence in db.execute('SELECT id,payload,evidence FROM mappings'):
                row=json.loads(payload);retained[key]=row['record_sha256']
                assert row['lexical_unit']==(row['source_lexical_unit'] and row['target_lexical_unit'])
                if key not in expected:continue
                envelope=json.loads(evidence)
                compiled,left,right=compile_record(envelope)
                assert row==compiled and envelope['record']['usage']['whole_reference'] is False
                assert row['lexical_unit'] is False
                for side,values in [('source',left),('target',right)]:
                    indexed={value for value, in db.execute('SELECT input FROM '+side+'_inputs WHERE mapping_id=?',(key,))}
                    assert indexed==set(values)
                assert envelope['record']['provenance']['baseline_catalog_sha256']==digest_file(baseline/'catalog.json')
                found.add(key);directions.add(identity);cases+=len(left)*len(right)
            assert all(retained.get(key)==sha for key,sha in previous.items())
            old_count+=len(previous)
    assert found==expected and len(directions)==38 and len(found)==2551
    assert before['references']==after['references']
    return {'schema':'vipi-attached-noun-static-audit-1','passed':True,
        'baseline_catalog_sha256':digest_file(baseline/'catalog.json'),
        'catalog_sha256':digest_file(current/'catalog.json'),'records_sha256':digest_file(authored),
        'new_records':len(found),'directions':len(directions),'finite_native_cases':cases,
        'retained_frame_records':old_count,'references_preserved':len(after['references']),
        'independent_linguistic_acceptance':False,'release_ready':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for option in ['baseline','current','authored','output']:parser.add_argument('--'+option,type=Path,required=True)
    args=parser.parse_args();result=audit(args.baseline,args.current,args.authored)
    with args.output.open('x') as output:json.dump(result,output,indent=2);output.write('\n')
    print(json.dumps(result))
