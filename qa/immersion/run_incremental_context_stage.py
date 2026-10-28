#!/usr/bin/env python3
"""Run a changed-language context build from a verified temporary disk corpus."""
import argparse,hashlib,json,os,shutil,subprocess,time
from pathlib import Path

def main(a):
    assert a.corpus.name=='corpus.sqlite' and a.corpus.is_file()
    pin=json.loads((a.corpus.parent/'receipt.json').read_text())
    receipt=a.working/'working-copy-receipt.json'
    file=a.working/'corpus.sqlite'
    if a.reuse_verified_working:
        record=json.loads(receipt.read_text())
        assert record['verified'] and not record['retired_after_build']
        assert record['source']==str(a.corpus)
        assert record['sha256']==pin['sha256'] and record['bytes']==pin['bytes']
        assert (a.working/'receipt.json').read_bytes()==(a.corpus.parent/'receipt.json').read_bytes()
        with file.open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
        assert actual==pin['sha256'] and file.stat().st_size==pin['bytes']
        print('Reusing hash-verified disk corpus from interrupted build.',flush=True)
    else:
        a.working.mkdir(parents=True,exist_ok=False)
        for name in ['receipt.json','ATTRIBUTION.txt']:
            source=a.corpus.parent/name
            if source.exists():shutil.copy2(source,a.working/name)
        start=time.monotonic();temporary=a.working/'corpus.sqlite.part'
        print('Copying pinned corpus to temporary disk storage.',flush=True)
        shutil.copyfile(a.corpus,temporary)
        with temporary.open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
        assert actual==pin['sha256'] and temporary.stat().st_size==pin['bytes']
        temporary.rename(file)
        record=dict(source=str(a.corpus),sha256=actual,bytes=file.stat().st_size,
            copy_seconds=time.monotonic()-start,verified=True,retired_after_build=False)
        receipt.write_text(json.dumps(record,indent=2)+'\n')
        print(json.dumps(record),flush=True)
    root=Path(__file__).resolve().parents[2]
    command=[str(root/'.venv-lexical-context/bin/python'),str(root/'qa/immersion/build_lexical_contexts.py'),
        '--shards',str(a.shards),'--corpus',str(file),'--output',str(a.output)]
    for language in a.pair_language:command+=['--pair-language',language]
    for supplement in a.supplement:command+=['--supplement',str(supplement)]
    scratch=a.working/'scratch';scratch.mkdir(exist_ok=a.reuse_verified_working)
    assert not list(scratch.iterdir()), 'Previous scratch output requires review before reuse'
    subprocess.run(command,cwd=root,env=dict(os.environ,TMPDIR=str(scratch)),stdin=subprocess.DEVNULL,check=True)
    file.unlink();shutil.rmtree(scratch)
    record['retired_after_build']=True;receipt.write_text(json.dumps(record,indent=2)+'\n')
    print('Verified source working duplicate retired after completed context build.',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['shards','corpus','working','output']:p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--reuse-verified-working',action='store_true')
    p.add_argument('--pair-language',action='append',required=True)
    p.add_argument('--supplement',action='append',type=Path,default=[])
    main(p.parse_args())
