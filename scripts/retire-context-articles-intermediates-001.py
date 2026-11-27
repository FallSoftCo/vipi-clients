#!/usr/bin/env python3
from pathlib import Path
from contextlib import closing
import hashlib, json, os, sqlite3, time

ROOT = Path("/aosp/development/vipi")
FINAL = ROOT / "artifacts/context-witnesses-014/witnesses.sqlite"
OUT = ROOT / "artifacts/context-articles-intermediate-retirement-001"


def sha(p):
    with p.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def readers(path):
    key = (path.stat().st_dev, path.stat().st_ino)
    result = []
    for process in Path("/proc").iterdir():
        if not process.name.isdigit():
            continue
        try:
            handles = list((process / "fd").iterdir())
        except (FileNotFoundError, PermissionError):
            continue
        for handle in handles:
            try:
                st = handle.stat()
            except (FileNotFoundError, PermissionError):
                continue
            if (st.st_dev, st.st_ino) == key:
                result.append(process.name)
    return result


receipt = json.loads(FINAL.with_name("receipt.json").read_text())
assert receipt["complete"] and sha(FINAL) == receipt["sha256"]
OUT.mkdir(exist_ok=False)
results = []
for n in range(1, 8):
    path = ROOT / f"artifacts/context-witnesses-articles-merge-{n:03d}/witnesses.sqlite"
    r = json.loads(path.with_name("receipt.json").read_text())
    assert r["complete"] and sha(path) == r["sha256"]
    assert not readers(path), "Intermediate still has an accessible open reader"
    with closing(
        sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
    ) as db:
        db.execute(
            "ATTACH DATABASE ? AS final",
            (FINAL.resolve().as_uri() + "?mode=ro&immutable=1",),
        )
        missing = db.execute("""SELECT 1 FROM main.witnesses w WHERE NOT EXISTS (
            SELECT 1 FROM final.witnesses f WHERE f.source=w.source AND f.target=w.target
            AND f.word=w.word AND f.counterpart=w.counterpart AND f.cue=w.cue
            AND f.support=w.support AND f.total=w.total) LIMIT 1""").fetchone()
        assert missing is None
        count = db.execute("SELECT count(*) FROM witnesses").fetchone()[0]
        assert count == r["counts"]["witnesses"]
    assert not readers(path)
    row = dict(
        file=str(path.relative_to(ROOT)),
        sha256=r["sha256"],
        bytes=path.stat().st_size,
        witness_rows_verified=count,
        successor_sha256=receipt["sha256"],
        retired=False,
    )
    record = OUT / (path.parent.name + ".json")
    record.write_text(json.dumps(row, indent=2) + "\n")
    path.unlink()
    row["retired"] = True
    record.write_text(json.dumps(row, indent=2) + "\n")
    results.append(row)
    print(json.dumps(row), flush=True)
(OUT / "receipt.json").write_text(
    json.dumps(
        dict(
            complete=True,
            files=results,
            freed_bytes=sum(r["bytes"] for r in results),
            retained="All original batches, complete final database, source contexts, compiler snapshots and per-stage receipts",
            proof="Every intermediate witness row, support and total exactly preserved in final; no accessible open reader at unlink",
        ),
        indent=2,
    )
    + "\n"
)
