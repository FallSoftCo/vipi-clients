#!/usr/bin/env python3
"""Immutable bounded adjective-context experiment; preserves all selected counterevidence."""
from pathlib import Path
import hashlib,json,shutil,subprocess
R=Path("/aosp/development/vipi");OUT=R/"artifacts/adjective-context-pilot-001";SNAP=OUT/"compiler-source"
def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def write(p,v):p.write_text(json.dumps(v,indent=2)+"\n")
OUT.mkdir(exist_ok=False);SNAP.mkdir();files=[]
for p in sorted((R/"language-packs").glob("*.py")):
    d=SNAP/p.name;shutil.copy2(p,d);files.append(dict(path=p.name,sha256=sha(d)))
write(SNAP/"receipt.json",dict(files=files))
write(OUT/"plan.json",dict(owner="01a16e0d-ac69-7dd0-872a-8cf087160515",
    dictionary_catalog_sha256=sha(R/"artifacts/lexical-present-verbs-001/catalog.json"),
    compiler_snapshot_sha256=sha(SNAP/"receipt.json"),languages=["en","es"],production_promoted=False,
    admission_basis="Filter 64 MiB, the noun filter measured 4,657,152 bytes for 218,118 spellings; adjective inventory is bounded by the same en/es shards. Observations 4 GiB: prior full observations including aggregates measured 3,189,723,136 bytes; this pass selects adjective spellings and omits frequencies/totals/witnesses. Remaining headroom covers SQLite temporaries.",
    observations_peak_bytes=4*1024**3))
def run(name,peak,args):
    with (OUT/(name+".log")).open("x") as log:
        subprocess.run(["storage-build","--peak-bytes",str(peak),"--",str(R/".venv-lexical-context/bin/python"),*map(str,args)],
            cwd=R,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,check=True)
run("filter",64*1024**2,[SNAP/"build_adjective_context_filter.py","--dictionary",R/"artifacts/lexical-present-verbs-001/catalog.json",
    "--kind","adjective","--output",R/"artifacts/adjective-source-words-001","--languages","en","es"])
run("observations",4*1024**3,[SNAP/"build_context_witnesses.py",
    "--contexts",R/"artifacts/lexical-contexts-present-pilot-001-tatoeba/contexts.sqlite",
    "--additional-context",R/"artifacts/lexical-contexts-present-pilot-001-pgv/contexts.sqlite",
    "--additional-corpus-receipt",R/"artifacts/parallel-global-voices-001/receipt.json",
    "--extra-context",R/"artifacts/lexical-contexts-present-pilot-001-massive/contexts.sqlite",
    "--extra-corpus-receipt",R/"artifacts/massive-corpus-003/receipt.json",
    "--source-exclusions",R/"artifacts/corpus-exclusions-001/hashes.sqlite",
    "--source-word-filter",R/"artifacts/adjective-source-words-001/source-words.sqlite","--observations-only",
    "--output",R/"artifacts/adjective-observations-001","--pair","en-es","--pair","es-en"])
receipt=R/"artifacts/adjective-observations-001/receipt.json";v=json.loads(receipt.read_text());assert v["complete"]
write(OUT/"receipt.json",dict(complete=True,observations_receipt_sha256=sha(receipt),counts=v["counts"],
    native_qualified=False,production_promoted=False))
print(json.dumps(dict(complete=True,counts=v["counts"])),flush=True)
