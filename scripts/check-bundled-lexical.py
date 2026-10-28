#!/usr/bin/env python3
"""Fail native builds when the pinned generated language assets are incomplete."""
import hashlib,itertools,json,re,sys
from pathlib import Path

def verify(root):
    manifest=json.loads((root/'catalog.json').read_text())
    assert manifest['schema']=='vipi-bundled-lexical-1'
    languages=manifest['languages']
    assert len(set(languages))==len(languages) and all(re.fullmatch('[a-z]{2,3}',x) for x in languages)
    expected={'d-'+x for x in languages}|{'w-'+a+'-'+b for a,b in itertools.combinations(sorted(languages),2)}
    rows=manifest['files']
    assert len(rows)==len(expected) and {r['id'] for r in rows}==expected
    assert manifest['directed_pairs']==len(languages)*(len(languages)-1)
    assert sum(r['compressed_bytes'] for r in rows)==manifest['compressed_bytes']
    assert sum(r['bytes'] for r in rows)==manifest['all_expanded_bytes']
    def sha(path):
        with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
    for row in rows:
        assert row['file']==row['id']+'.sqlite.zlib'
        file=root/row['file']
        assert file.is_file() and file.stat().st_size==row['compressed_bytes'],str(file)
        assert sha(file)==row['compressed_sha256'],str(file)
    assert (root/'ATTRIBUTION.txt').stat().st_size>0
    assert sha(root/'compatibility.json')==manifest['compatibility_sha256']
    print(f"Verified bundled language assets: {len(languages)} languages, {len(rows)} files, {manifest['compressed_bytes']} compressed bytes.")
if __name__=='__main__':
    root=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parents[1]/'data/lexical'
    try:verify(root)
    except (AssertionError,OSError,KeyError,ValueError) as error:
        raise SystemExit(f"Language bundle is missing or inconsistent: {error}. Restore the generated assets matching data/lexical/catalog.json; see docs/BULK_LANGUAGE_EXPANSION.md.")
