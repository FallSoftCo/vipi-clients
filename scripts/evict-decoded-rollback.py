#!/usr/bin/env python3
"""Remove an idle decoded duplicate only after verifying its retained compressed copy."""
import argparse,hashlib,json,os,stat,subprocess,zlib
from pathlib import Path
R=Path("/aosp/development/vipi")
def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def save(p,v):
    stage=p.with_suffix(".tmp");stage.write_text(json.dumps(v,indent=2)+"\n")
    with stage.open("rb") as f:os.fsync(f.fileno())
    stage.replace(p)
p=argparse.ArgumentParser(description=__doc__)
p.add_argument("--dictionary",required=True);p.add_argument("--bundle",required=True);p.add_argument("--output",required=True)
args=p.parse_args()
root=R/"artifacts"/args.dictionary;bundle=R/"artifacts"/args.bundle;out=R/"artifacts"/args.output
assert root.parent==bundle.parent==out.parent==R/"artifacts"
current=json.loads((R/"data/lexical/catalog.json").read_text())
catalog=json.loads((root/"catalog.json").read_text());packed=json.loads((bundle/"catalog.json").read_text())
assert catalog["release_id"]==packed["dictionary_release"]!=current["dictionary_release"]
qualified=R/"artifacts/bundled-lexical-009-qualification.json"
assert sha(qualified)=="0db44c51384cf3f0bc084e66934caea5a54f998149f48b9d2cbb1bb87f7b9c5a"
assert sha(R/"data/lexical/catalog.json")=="6b8040ae0eacb82dded24d9cf948649551195165d3d1c12a085e17e02e847300"
assert json.loads(qualified.read_text())["accepted_for_development"]
out.mkdir(exist_ok=False);rows=[];packed_rows={r["id"]:r for r in packed["files"]}
for row in catalog["shards"]:
    path=root/(row["language"]+".sqlite");archive=packed_rows["d-"+row["language"]];compressed=bundle/archive["file"]
    assert path.is_file() and not path.is_symlink() and path.stat().st_nlink==1
    assert compressed.is_file() and not compressed.is_symlink()
    assert row["sha256"]==archive["sha256"] and row["bytes"]==archive["bytes"]==path.stat().st_size
    assert sha(path)==row["sha256"] and sha(compressed)==archive["compressed_sha256"]
    decoder=zlib.decompressobj();digest=hashlib.sha256();n=0
    with compressed.open("rb") as f:
        while chunk:=f.read(1024*1024):
            data=decoder.decompress(chunk);digest.update(data);n+=len(data)
        data=decoder.flush();digest.update(data);n+=len(data)
    assert decoder.eof and not decoder.unused_data and digest.hexdigest()==row["sha256"] and n==row["bytes"]
    idle=subprocess.run(["fuser",str(path)],stdin=subprocess.DEVNULL,capture_output=True)
    assert idle.returncode==1 and not idle.stdout and not idle.stderr, "File may be in active use"
    info=path.stat()
    rows.append(dict(path=str(path),bytes=n,sha256=row["sha256"],inode=info.st_ino,device=info.st_dev,
        retained_compressed_path=str(compressed),compressed_sha256=archive["compressed_sha256"],
        decompressed_byte_identity_verified=True,removed=False))
receipt=dict(complete=False,kind="redundant_decoded_rollback_copy_eviction",accepted_current="bundled-lexical-009",
    compressed_rollback_retained=True,source_catalog_retained=True,files=rows,
    catalog_sha256=sha(root/"catalog.json"),compressed_catalog_sha256=sha(bundle/"catalog.json"),reclaimed_bytes=0)
save(out/"receipt.json",receipt)
for row in rows:
    path=Path(row["path"]);info=path.stat()
    assert (info.st_dev,info.st_ino,info.st_size,info.st_nlink)==(row["device"],row["inode"],row["bytes"],1)
    assert sha(Path(row["retained_compressed_path"]))==row["compressed_sha256"]
    idle=subprocess.run(["fuser",str(path)],stdin=subprocess.DEVNULL,capture_output=True)
    assert idle.returncode==1 and not idle.stdout and not idle.stderr
    path.unlink();row["removed"]=True;receipt["reclaimed_bytes"]+=row["bytes"];save(out/"receipt.json",receipt)
receipt["complete"]=True;save(out/"receipt.json",receipt)
print(json.dumps(dict(complete=True,reclaimed_bytes=receipt["reclaimed_bytes"])),flush=True)
