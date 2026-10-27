#!/usr/bin/env python3
"""Create/apply verified QA fixture deltas; not a signed production updater."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess


def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1048576),b''):digest.update(block)
    return digest.hexdigest()


def manifest(root):
    result=json.loads((root/'manifest.json').read_text())
    assert result['schema']=='vipi-lexical-qualification-1'
    assert sha(root/'cases.json')==result['cases_sha256']
    assert len({r['language'] for r in result['shards']})==len(result['shards'])
    assert all(re.fullmatch('[a-z]{2}',r['language']) for r in result['shards'])
    return result


def create(base,new,output,zstd):
    old=manifest(base);current=manifest(new);output.mkdir(parents=True,exist_ok=False)
    previous={r['language']:r for r in old['shards']};rows=[]
    for row in current['shards']:
        language=row['language'];before=base/(language+'.sqlite');after=new/(language+'.sqlite')
        assert sha(before)==previous[language]['sha256'] and sha(after)==row['sha256']
        patch=output/(language+'.patch.zst')
        subprocess.run([zstd,'-q','-T2','-3','--patch-from='+str(before),str(after),'-o',str(patch)],check=True)
        rows.append(dict(language=language,base_sha256=previous[language]['sha256'],sha256=row['sha256'],
            bytes=row['bytes'],patch_sha256=sha(patch),patch_bytes=patch.stat().st_size))
    for name in ('manifest.json','cases.json'):shutil.copyfile(new/name,output/name)
    (output/'patches.json').write_text(json.dumps(dict(schema='vipi-qa-delta-1',files=rows,
        manifest_sha256=sha(output/'manifest.json')),indent=2)+'\n')
    print(json.dumps(dict(files=len(rows),patch_bytes=sum(r['patch_bytes'] for r in rows))))


def apply(base,patches,output,zstd):
    before=manifest(base);current=manifest(patches)
    delta=json.loads((patches/'patches.json').read_text());assert delta['schema']=='vipi-qa-delta-1'
    assert delta['manifest_sha256']==sha(patches/'manifest.json')
    expected={r['language']:r for r in current['shards']};old={r['language']:r for r in before['shards']}
    assert len(delta['files'])==len(expected) and {r['language'] for r in delta['files']}==set(expected)
    output.mkdir(parents=True,exist_ok=False)
    for row in delta['files']:
        language=row['language'];reference=base/(language+'.sqlite');patch=patches/(language+'.patch.zst')
        assert row['sha256']==expected[language]['sha256'] and row['bytes']==expected[language]['bytes']
        assert row['base_sha256']==old[language]['sha256']==sha(reference)
        assert patch.stat().st_size==row['patch_bytes'] and sha(patch)==row['patch_sha256']
        target=output/(language+'.sqlite')
        subprocess.run([zstd,'-q','-d','--memory=1024MB','--patch-from='+str(reference),str(patch),'-o',str(target)],check=True)
        assert target.stat().st_size==row['bytes'] and sha(target)==row['sha256']
    for name in ('manifest.json','cases.json'):shutil.copyfile(patches/name,output/name)
    print(json.dumps(dict(verified=True,files=len(delta['files']),manifest_sha256=sha(output/'manifest.json'))))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['create','apply'])
    for name in ('base','input','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--zstd',default='zstd');args=parser.parse_args()
    (create if args.action=='create' else apply)(args.base,args.input,args.output,args.zstd)
