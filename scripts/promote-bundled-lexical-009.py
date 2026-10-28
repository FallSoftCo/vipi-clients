#!/usr/bin/env python3
"""Activate the completely built candidate assets for native development QA."""
from pathlib import Path
import hashlib,json,os,subprocess,time
ROOT=Path('/aosp/development/vipi')
def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
    os.chdir(ROOT)
    source=ROOT/'artifacts/bundled-lexical-009'
    built=json.loads((ROOT/'artifacts/korean-context-release-001/receipt.json').read_text())
    assert built['complete'] and sha(source/'catalog.json')==built['bundle_sha256']
    current=ROOT/'data/lexical'
    assert sha(current/'catalog.json')=='de29102504ad79d40442609507b2bbf385fc07be21590adb12bd077cb8ff31ba'
    subprocess.run(['python3','scripts/check-bundled-lexical.py',str(source)],check=True)
    candidate=ROOT/'.runtime/bundled-lexical-candidate-009'
    previous=ROOT/'.runtime/previous-bundled-lexical-008'
    receipt=ROOT/'artifacts/bundled-lexical-promotion-009.json'
    assert not previous.exists() and not receipt.exists()
    candidate.mkdir(exist_ok=False)
    for p in source.iterdir():
        assert p.is_file()
        os.link(p,candidate/p.name)
    # Keep repository text formatting without mutating the immutable artifact.
    attribution=candidate/'ATTRIBUTION.txt';text=attribution.read_text().rstrip()+'\n'
    attribution.unlink();attribution.write_text(text)
    old_sha=sha(current/'catalog.json')
    current.rename(previous)
    try:candidate.rename(current)
    except BaseException:
        previous.rename(current);raise
    result=dict(complete=True,previous_catalog_sha256=old_sha,
        candidate_catalog_sha256=sha(current/'catalog.json'),retained_previous=str(previous),
        source_release=str(source),development_only=True,native_qualified=False,
        semantic_accuracy_claim=False,store_ready=False,at=time.time())
    receipt.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
