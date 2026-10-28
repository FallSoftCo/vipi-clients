#!/usr/bin/env python3
"""Build every directed pair from freshly recompiled contexts, with bounded disk stages.

No automatic retries. An incomplete stage requires inspection. This release
does not reuse historical success rows or change agreement thresholds.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import itertools
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import time

ROOT=Path('/aosp/development/vipi')
PYTHON=str(ROOT/'.venv-lexical-context/bin/python')
OUTPUT=ROOT/'artifacts/context-articles-release-001'
SNAPSHOT=OUTPUT/'compiler-source'
LANGUAGES=['ar','de','en','es','fr','it','ja','ko','pt','sw','zh']
FILES=['language-packs/build_context_witnesses.py','language-packs/replace_context_witness_pairs.py',
       'language-packs/export_context_pair_packs.py','language-packs/bundle_lexical_data.py',
       'language-packs/build_wiktextract.py','language-packs/context_hints.py']
def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def checked(name):
    folder=ROOT/'artifacts'/name
    receipt=json.loads((folder/'receipt.json').read_text())
    assert receipt['complete'] and receipt['sha256']==sha(folder/'witnesses.sqlite')
    return receipt
def verify_code():
    for row in json.loads((SNAPSHOT/'receipt.json').read_text())['files']:
        assert sha(ROOT/row['file'])==row['sha256'],row['file']
def run(name,peak,command):
    verify_code()
    with (ROOT/'artifacts'/(name+'.log')).open('x') as log:
        result=subprocess.run(['storage-build','--peak-bytes',str(peak),'--',PYTHON,*command],
            cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL)
    assert result.returncode==0,(name,result.returncode)
def compile_batch(row):
    name=row['revision']
    command=['language-packs/build_context_witnesses.py',
        '--contexts','artifacts/lexical-contexts-articles-001/contexts.sqlite',
        '--additional-context','artifacts/lexical-contexts-pgv-articles-001/contexts.sqlite',
        '--additional-corpus-receipt','artifacts/parallel-global-voices-001/receipt.json',
        '--source-exclusions','artifacts/corpus-exclusions-001/hashes.sqlite',
        '--base-supplement-receipt','artifacts/swahili-corpus-001/receipt.json',
        '--output','artifacts/'+name]
    for pair in row['pairs']:command+=['--pair',pair]
    run(name,row['peak_bytes'],command)
    receipt=checked(name)
    assert set(receipt['requested_pairs'])==set(row['pairs'])
    assert receipt['minimum_support']==3 and receipt['minimum_agreement']==.98
    path=ROOT/'artifacts'/name/'observations.sqlite'
    assert sha(path)==receipt['observations_sha256'] and path.stat().st_size==receipt['observations_bytes']
    # The completed subprocess closed all SQLite handles. This derived work
    # table is reproducible from retained exact contexts and compiler; final
    # witnesses retain counts and attributed examples.
    retirement=dict(file=path.name,sha256=receipt['observations_sha256'],
        bytes=receipt['observations_bytes'],successor_sha256=receipt['sha256'],
        source_contexts_sha256=receipt['source_contexts_sha256'],
        additional_contexts_sha256=receipt['additional_contexts_sha256'],
        compiler_sha256=receipt['compiler_sha256'],complete=False)
    record=path.parent/'observations-retirement.json';write(record,retirement)
    path.unlink();retirement['complete']=True;write(record,retirement)
    print(json.dumps(dict(stage='compiled',revision=name,rules=receipt['counts']['witnesses'],bytes=receipt['bytes'])),flush=True)
    return name
def main():
    assert subprocess.check_output(['hostname'],text=True).strip()=='ozzz-aosp'
    os.chdir(ROOT);OUTPUT.mkdir(exist_ok=False);SNAPSHOT.mkdir()
    sources=[]
    for relative in FILES:
        source=ROOT/relative;target=SNAPSHOT/relative;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target);sources.append(dict(file=relative,sha256=sha(source)))
    write(SNAPSHOT/'receipt.json',dict(files=sources))
    contexts=[json.loads((ROOT/'artifacts'/name/'receipt.json').read_text())
        for name in ['lexical-contexts-articles-001','lexical-contexts-pgv-articles-001']]
    catalog=json.loads((ROOT/'artifacts/lexical-shards-012/catalog.json').read_text())
    assert all(r['complete'] and not r['pilot'] and r['source_release_id']==catalog['release_id'] for r in contexts)
    unordered=['-'.join(pair) for pair in itertools.combinations(LANGUAGES,2)]
    counts={pair:sum(r['pairs'].get(pair,0) for r in contexts) for pair in unordered}
    groups=[];group=[];total=0
    for pair,count in sorted(counts.items(),key=lambda row:row[1],reverse=True):
        if group and total+count>2400000:groups.append(group);group=[];total=0
        group.append(pair);total+=count
    if group:groups.append(group)
    groups.reverse()
    rows=[]
    for number,group in enumerate(groups,1):
        count=sum(counts[p] for p in group)
        rows.append(dict(revision=f'context-witnesses-articles-batch-{number:03d}',
            pairs=sorted(d for p in group for d in (p,'-'.join(reversed(p.split('-'))))),
            candidate_alignments=count,peak_bytes=(6 if count>2400000 else 4)*1024**3))
    write(OUTPUT/'plan.json',dict(owner='01a16e0d-ac69-7dd0-872a-8cf087160515',
        batches=rows,source_catalog_sha256=sha(ROOT/'artifacts/lexical-shards-012/catalog.json'),
        contexts_sha256=[r['sha256'] for r in contexts],compiler_snapshot_sha256=sha(SNAPSHOT/'receipt.json'),
        driver_sha256=sha(Path(__file__)),expected_directions=110,
        basis='Prior cumulative witness builds used 4 GiB per 2.4 million candidate alignments and 6 GiB for the larger English-Spanish batch; source context bytes are already allocated.'))
    with ThreadPoolExecutor(max_workers=2) as executor:
        for future in as_completed([executor.submit(compile_batch,row) for row in rows]):future.result()
    parent=rows[0]['revision']
    for number,row in enumerate(rows[1:],1):
        target=f'context-witnesses-articles-merge-{number:03d}'
        run(target,2*1024**3,['language-packs/replace_context_witness_pairs.py',
            '--base',f'artifacts/{parent}/witnesses.sqlite',
            '--replacement',f'artifacts/{row["revision"]}/witnesses.sqlite','--output','artifacts/'+target])
        checked(target);parent=target
    receipt=checked(parent);expected={a+'-'+b for a,b in itertools.permutations(LANGUAGES,2)}
    assert set(receipt['pair_input_revisions'])==expected and set(receipt['requested_pairs'])==expected
    assert receipt['source_release_id']==catalog['release_id']
    final=ROOT/'artifacts/context-witnesses-014';final.mkdir(exist_ok=False)
    for name in ['witnesses.sqlite','receipt.json','ATTRIBUTION.txt']:os.link(ROOT/'artifacts'/parent/name,final/name)
    run('context-pair-packs-014',512*1024**2,['language-packs/export_context_pair_packs.py',
        '--source',str(final/'witnesses.sqlite'),'--catalog','artifacts/lexical-shards-012/catalog.json',
        '--output','artifacts/context-pair-packs-014'])
    run('bundled-lexical-003',768*1024**2,['language-packs/bundle_lexical_data.py',
        '--base','artifacts/lexical-shards-012/catalog.json','--catalog','artifacts/lexical-shards-012/catalog.json',
        '--contexts','artifacts/context-pair-packs-014/catalog.json','--output','artifacts/bundled-lexical-003'])
    bundle=json.loads((ROOT/'artifacts/bundled-lexical-003/catalog.json').read_text())
    write(OUTPUT/'receipt.json',dict(complete=True,final_witnesses_sha256=receipt['sha256'],
        rules=receipt['counts']['witnesses'],directions=110,bundle_sha256=sha(ROOT/'artifacts/bundled-lexical-003/catalog.json'),
        compressed_bytes=bundle['compressed_bytes'],native_qualified=False,semantic_accuracy_claim=False))
    print(json.dumps(dict(complete=True,compressed_bytes=bundle['compressed_bytes'],directions=110)),flush=True)
if __name__=='__main__':main()
