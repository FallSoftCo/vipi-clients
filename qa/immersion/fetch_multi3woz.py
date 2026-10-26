#!/usr/bin/env python3
"""Acquire the publisher's pinned dialogue archive with durable provenance.

No corpus text is inspected or approved here. Keep the official train/dev/test
partitions and culturally adapted names separate from literal translation data.
"""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request
import zipfile
from conversation_corpus import sha_file,write_json

REVISION='c65e80fe120704125255de5cf582a51ebaa285cd'
REPOSITORY='cambridgeltl/multi3woz'
ARCHIVE_BYTES=90631848
ARCHIVE_GIT_BLOB='330ba2b6c2e2defb4a84efafd28100ec7a020023'


def main(output):
    output.mkdir(parents=True,exist_ok=False);assets=[]
    for name,bound in [('LICENSE',16384),('README.md',65536),('data.zip',ARCHIVE_BYTES)]:
        url=f'https://raw.githubusercontent.com/{REPOSITORY}/{REVISION}/{name}'
        path=output/name;temporary=path.with_suffix(path.suffix+'.part');count=0
        with urllib.request.urlopen(url,timeout=60) as response,temporary.open('xb') as stream:
            while chunk:=response.read(1024*1024):
                count+=len(chunk)
                if count>bound:raise ValueError('Publisher asset exceeds inspected size bound')
                stream.write(chunk)
        if name=='data.zip':
            if count!=ARCHIVE_BYTES:raise ValueError('Archive size mismatch')
            blob=hashlib.sha1(f'blob {count}\0'.encode())
            with temporary.open('rb') as stream:
                while chunk:=stream.read(1024*1024):blob.update(chunk)
            if blob.hexdigest()!=ARCHIVE_GIT_BLOB:raise ValueError('Publisher Git blob mismatch')
        temporary.rename(path);assets.append({'file':name,'url':url,'bytes':count,'sha256':sha_file(path)})
    if not (output/'LICENSE').read_text().startswith('MIT License'):raise ValueError('Unexpected license')
    with zipfile.ZipFile(output/'data.zip') as archive:
        members=[{'name':x.filename,'bytes':x.file_size,'compressed_bytes':x.compress_size} for x in archive.infolist()]
        if any(Path(x['name']).is_absolute() or '..' in Path(x['name']).parts for x in members):
            raise ValueError('Unsafe member path')
    receipt={'schema':'vipi-multi3woz-source-1','repository':REPOSITORY,'revision':REVISION,
        'license':'MIT (repository LICENSE; inspect any archive-specific notices before use)',
        'attribution':'Songbo Hu and Multi3WOZ contributors; retained LICENSE and README',
        'assets':assets,'archive_members':members,'data_text_inspected':False,'linguistic_acceptance':False,
        'limits':['Task-oriented, culturally adapted dialogue; not general friend chat or literal parallel translations.',
            'No training, mapping import, native evaluation or publication is performed by acquisition.']}
    write_json(output/'receipt.json',receipt)
    print(json.dumps({'revision':REVISION,'downloaded_bytes':sum(x['bytes'] for x in assets),
        'archive_members':len(members),'uncompressed_bytes':sum(x['bytes'] for x in members),
        'receipt_sha256':sha_file(output/'receipt.json')}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    main(p.parse_args().output)
