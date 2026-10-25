#!/usr/bin/env python3
"""Acquire the pinned research databases with their inseparable provenance.

Run on OZZZ-OS with storage-build. This does not install a production pack or
approve the multilingual sources for redistribution or contextual substitution.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import time
import urllib.request

from build_wiktextract import digest_file


def bounded_copy(source, destination, expected):
    size = 0
    with destination.open('xb') as output:
        while chunk := source.read(min(1024 * 1024, expected - size + 1)):
            size += len(chunk)
            if size > expected:
                raise ValueError('Source exceeds pinned size')
            output.write(chunk)
    if size != expected:
        raise ValueError('Source is shorter than pinned size')


def main(args):
    pin_path = Path(__file__).parent / 'sources/cygnet-20260512.json'
    pinned = json.loads(pin_path.read_text())
    args.output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic(); assets = []
    for asset in pinned['assets']:
        compressed = args.output / asset['name']
        request = urllib.request.Request(asset['url'], headers={'User-Agent':'Vipi-source-qualification'})
        with urllib.request.urlopen(request, timeout=60) as response:
            if response.status != 200:
                raise ValueError('Full asset response required')
            bounded_copy(response, compressed, asset['bytes'])
        if digest_file(compressed) != asset['sha256']:
            raise ValueError('Release asset checksum mismatch')
        database = compressed.with_suffix('')
        with gzip.open(compressed, 'rb') as source:
            bounded_copy(source, database, asset['uncompressed_bytes'])
        with sqlite3.connect(database.resolve().as_uri()+'?mode=ro&immutable=1', uri=True) as db:
            db.execute('PRAGMA trusted_schema=OFF')
            if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                raise ValueError('Database integrity failure')
        entry = dict(asset, database=database.name, database_sha256=digest_file(database))
        assets.append(entry)
        print(json.dumps({'verified':database.name,'bytes':asset['uncompressed_bytes'],
                          'sha256':entry['database_sha256']}), flush=True)
    receipt = {'source':pinned,'assets':assets,'seconds':time.monotonic()-started,
               'pin_sha256':digest_file(pin_path),'compiler_sha256':digest_file(Path(__file__)),
               'runtime_integration':False,'linguistic_acceptance':False,
               'redistribution_qualification':False}
    (args.output/'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'complete':True,'seconds':receipt['seconds']}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    main(parser.parse_args())
