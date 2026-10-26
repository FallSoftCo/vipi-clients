#!/usr/bin/env python3
"""Complete lexical compounds with independently stated scope, not verb frames.

The six chosen meanings already have exact native forms and Latin readings.
This batch requires a NEW scope assessment. It cannot inherit approval from
the old request construction, nor supply an unseen whole-sentence translation.
"""
import argparse
from copy import deepcopy
from pathlib import Path
import authored_needs_frames as needs
import authored_request_frames as requests
from build_wiktextract import canonical, digest_file
from mapping_catalog import validate

SOURCES = [(needs,'11db9924b33b43502060eaa4a2ef99f88fbca335b070d0b1e042e14887ed0e02',
            ['needs_address','needs_phone_number','needs_phone_charger','needs_door_key']),
           (requests,'f2554aad746126b6102e4ec9d9c7d4326c771a807dd8dd42eaebec7f2a5f0ab3',
            ['requests_train_ticket_request','requests_hotel_room_request'])]


def records():
    for module, expected, topics in SOURCES:
        if digest_file(Path(module.__file__)) != expected: raise ValueError('Changed source authoring')
        for row in module.records():
            if row['logical_id'].endswith(':sw-first-person-contraction'): continue
            topic=next((t for t in topics if row['logical_id'].startswith('vipi-authored-r1:'+t+':')),None)
            if topic is None: continue
            row=deepcopy(row)
            row['logical_id']='vipi-compound-unit-r1:'+topic+':'+row['source_language']+':'+row['target_language']
            row['usage'].update(lexical_unit=True,
                context_generalization='explicitly assessed complete noun compound; surrounding verb not required',
                source_frame_span=row['source_span'][:], target_frame_span=row['target_span'][:],
                source_frame_pattern=[{'focus':row['source']}],target_frame_pattern=[{'focus':row['target']}],
                permitted_context=row['meaning']+'; the entire compound must appear as a unique native window on both sides. Surrounding person, tense, negation and ownership stay unchanged.',
                abstain_when=['Either complete native compound is absent.',
                    'Repeated source or target occurrences leave alignment uncertain.',
                    'Competing source meanings or readings disagree.',
                    'The compound overlaps a protected identifier or exceeds the native boundary/window constraints.'])
            row['provenance']['scope_source']='Existing compound forms '+expected+'; new explicit scope assessment required'
            row['provenance']['priority_basis']='Six independently chosen complete everyday compounds; no inspected evaluation utterance supplied a string'
            validate(row); yield row


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    rows=list(records());assert len(rows)==660
    path=args.output/'records.jsonl';path.write_text(''.join(canonical(r)+'\n' for r in rows))
    print(canonical({'records':len(rows),'records_sha256':digest_file(path),
        'authoring_source_sha256':digest_file(Path(__file__)),'release_ready':False}))
