#!/usr/bin/env python3
"""Measure deterministic ZIP downloads and verify decompressed payload identity."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main(args):
    catalog = json.loads(args.catalog.read_text())
    entries = catalog.get('shards', catalog.get('pair_packs'))
    assert entries
    args.output.mkdir(parents=True, exist_ok=False)
    rows = []
    for entry in entries:
        name = entry.get('file', entry.get('language', '') + '.sqlite')
        source = args.catalog.parent / name
        assert source.stat().st_size == entry['bytes'] and sha(source) == entry['sha256']
        path = args.output / (name + '.zip')
        info = zipfile.ZipInfo(name, date_time=(2026, 10, 27, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        with zipfile.ZipFile(path, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
            with archive.open(info, 'w', force_zip64=True) as destination, source.open('rb') as stream:
                while block := stream.read(1024 * 1024):
                    destination.write(block)
        with zipfile.ZipFile(path) as archive, archive.open(name) as stream:
            assert hashlib.file_digest(stream, 'sha256').hexdigest() == entry['sha256']
        row = dict(file=path.name, bytes=path.stat().st_size, sha256=sha(path),
                   payload=name, payload_bytes=entry['bytes'], payload_sha256=entry['sha256'])
        rows.append(row)
        print(json.dumps(row), flush=True)
    receipt = dict(schema='vipi-measured-zip-downloads-1', complete=True, roundtrip_sha256_verified=True,
                   input_catalog_sha256=sha(args.catalog), compiler_sha256=sha(Path(__file__)),
                   payload_bytes=sum(r['payload_bytes'] for r in rows), download_bytes=sum(r['bytes'] for r in rows),
                   files=rows, signed=False, production_installer_qualified=False,
                   limitation='Measured ZIP assets, not store-computed app download size; no release activation.')
    (args.output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({k: v for k, v in receipt.items() if k != 'files'}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('catalog', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    main(parser.parse_args())
