#!/usr/bin/env python3
"""Package a verified subset of qualification packs for native replay.

The supplied key is a QA fixture key, never a production trust decision.
"""
import argparse
import json
from pathlib import Path
import tarfile
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import ec
from conversation_corpus import sha_file,write_json


def main(a):
    languages=['en','es','fr','de','it','pt','ar','zh','ja','ko']
    if len(a.run)!=3 or not a.run.isascii() or not a.run.isdigit():raise ValueError('Three digit QA run required')
    if not a.sources or len(set(a.sources))!=len(a.sources) or not set(a.sources)<=set(languages):raise ValueError('Invalid source languages')
    keypath=a.packs/'signing-public-key.der';key=serialization.load_der_public_key(keypath.read_bytes())
    if not isinstance(key,ec.EllipticCurvePublicKey) or not isinstance(key.curve,ec.SECP256R1):raise ValueError('Expected QA P256 key')
    files=[keypath];manifests=[]
    for source in a.sources:
        for target in languages:
            if source==target:continue
            pair=source+'-'+target;folder=a.packs/pair
            data=(folder/'manifest.json').read_bytes();manifest=json.loads(data)
            key.verify((folder/'manifest.sig').read_bytes(),data,ec.ECDSA(hashes.SHA256()))
            if manifest['pack_id']!=pair or manifest['schema_version']!=4 or manifest['context_policy'] not in ('all-source-senses-veto-3','all-source-senses-native-guards-veto-4'):raise ValueError('Wrong pack policy')
            guarded=manifest['context_policy']=='all-source-senses-native-guards-veto-4'
            if guarded != ('native_source_guard_policy' in manifest):raise ValueError('Guard policy must not be silently ignored')
            if guarded and (source!='zh' or manifest['native_source_guard_policy']!='attested-native-han-lexeme-and-polysemy-veto-1'):raise ValueError('Wrong native guard policy')
            if manifest['key_id']!='bilingual-qualification-'+a.run:raise ValueError('Wrong fixture key ID')
            if sha_file(folder/'vocabulary.sqlite')!=manifest['sha256']:raise ValueError('Pack checksum mismatch')
            if (folder/'vocabulary.sqlite').stat().st_size!=manifest['bytes']:raise ValueError('Pack size mismatch')
            files.extend(folder/name for name in ('manifest.json','manifest.sig','vocabulary.sqlite','ATTRIBUTION.txt'))
            manifests.append(manifest)
    if any(not p.is_file() or p.is_symlink() for p in files):raise ValueError('Regular fixture files required')
    a.output.mkdir(parents=True,exist_ok=False)
    archive=a.output/'packs.tar.gz'
    with tarfile.open(archive,'w:gz',compresslevel=3) as out:
        for path in files:out.add(path,arcname='packs-'+a.run+'/'+str(path.relative_to(a.packs)),recursive=False)
    write_json(a.output/'receipt.json',{'schema':'vipi-qa-pack-subset-1','qualification_only':True,
        'sources':a.sources,'pairs':len(manifests),'files':len(files),'uncompressed_bytes':sum(p.stat().st_size for p in files),
        'archive_bytes':archive.stat().st_size,'archive_sha256':sha_file(archive),'signing_public_key_sha256':sha_file(keypath),
        'pack_manifests':manifests,'stager_sha256':sha_file(Path(__file__))})
    print(json.dumps({'pairs':len(manifests),'uncompressed_bytes':sum(p.stat().st_size for p in files),'archive_bytes':archive.stat().st_size,'archive_sha256':sha_file(archive)}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--packs',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--run',required=True);p.add_argument('--sources',nargs='+',required=True)
    main(p.parse_args())
