#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,os,zlib
ROOT=Path("/aosp/development/vipi")
BASE=ROOT/"artifacts/lexical-shards-012"
BUNDLE=ROOT/"artifacts/bundled-lexical-003"
OUT=ROOT/"artifacts/dictionary-012-retirement-001"
def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def readers(path):
    key=(path.stat().st_dev,path.stat().st_ino);result=[]
    for process in Path("/proc").iterdir():
        if not process.name.isdigit():continue
        try:handles=list((process/"fd").iterdir())
        except (FileNotFoundError,PermissionError):continue
        for handle in handles:
            try:st=handle.stat()
            except (FileNotFoundError,PermissionError):continue
            if (st.st_dev,st.st_ino)==key:result.append(process.name)
    return result
catalog=json.loads((BASE/"catalog.json").read_text())
bundle=json.loads((BUNDLE/"catalog.json").read_text())
assert catalog["release_id"]==bundle["dictionary_release"]
OUT.mkdir(exist_ok=False)
rows=[]
for shard in catalog["shards"]:
    language=shard["language"];raw=BASE/(language+".sqlite")
    row=next(r for r in bundle["files"] if r["id"]=="d-"+language)
    compressed=BUNDLE/row["file"]
    assert sha(compressed)==row["compressed_sha256"]
    decoder=zlib.decompressobj();digest=hashlib.sha256();length=0
    with compressed.open("rb") as stream:
        while data:=stream.read(65536):
            chunk=decoder.decompress(data);digest.update(chunk);length+=len(chunk)
        chunk=decoder.flush();digest.update(chunk);length+=len(chunk)
    assert decoder.eof and not decoder.unused_data
    assert length==row["bytes"]==shard["bytes"]==raw.stat().st_size
    assert digest.hexdigest()==row["sha256"]==shard["sha256"]==sha(raw)
    assert not readers(raw)
    record=dict(file=str(raw.relative_to(ROOT)),sha256=shard["sha256"],bytes=length,
        links_before=raw.stat().st_nlink,exact_compressed_replacement=str(compressed.relative_to(ROOT)),
        compressed_sha256=row["compressed_sha256"],retired=False)
    output=OUT/(language+".json");output.write_text(json.dumps(record,indent=2)+"\n")
    raw.unlink();record["retired"]=True;output.write_text(json.dumps(record,indent=2)+"\n")
    rows.append(record);print(json.dumps(record),flush=True)
(OUT/"receipt.json").write_text(json.dumps(dict(complete=True,files=rows,
    logical_bytes_retired=sum(r["bytes"] for r in rows),
    bytes_without_other_hardlinks=sum(r["bytes"] for r in rows if r["links_before"]==1),
    retained="Exact compressed payloads, catalog, attribution and all provenance"),indent=2)+"\n")
