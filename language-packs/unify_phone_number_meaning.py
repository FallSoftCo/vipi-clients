#!/usr/bin/env python3
"""Reassess an identical telephone-number sense under one existing identity.

Only the meaning description changes. Patterns, native forms, readings, whole
references and scope stay unchanged. Runtime ambiguity checks are untouched.
"""
import argparse
from copy import deepcopy
from pathlib import Path
import authored_compound_units as units
import extend_needs_request_forms as needs
from build_wiktextract import canonical, digest_file
from mapping_catalog import validate

MEANING='a number identifying a telephone connection, not a count, musical number or generic identifier'
SOURCES=[(needs,'8c70715a281d5993e682b050186941a19a004c1d1cbf5c652da080e303ce3d6b','vipi-authored-r1:needs_phone_number:'),
         (units,'612c704999b28bb842520b2b6df7cf655ee8f90ff4b554edce7d542f3de85061','vipi-compound-unit-r1:needs_phone_number:')]


def records():
    for module,expected,prefix in SOURCES:
        if digest_file(Path(module.__file__))!=expected:raise ValueError('Changed source batch')
        for original in module.records():
            if not original['logical_id'].startswith(prefix):continue
            row=deepcopy(original)
            if row['meaning']!='a number used to call a telephone':raise ValueError('Unassessed prior meaning')
            row['meaning']=MEANING
            validate(row);yield row


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    rows=list(records());assert len(rows)==260
    path=args.output/'records.jsonl';path.write_text(''.join(canonical(r)+'\n' for r in rows))
    print(canonical({'records':len(rows),'records_sha256':digest_file(path),
        'authoring_source_sha256':digest_file(Path(__file__)),'release_ready':False}))
