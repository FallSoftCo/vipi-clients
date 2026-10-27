#!/usr/bin/env python3
"""Extend the diagnostic fixture with authored noun/carrier ambiguity checks."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

def main(a):
    manifest=json.loads((a.base/"manifest.json").read_text())
    assert sha(a.base/"cases.json")==manifest["cases_sha256"]
    cases=json.loads((a.base/"cases.json").read_text())
    examples=[
        dict(id="noun-geometry-wedding-attend",original="I will attend the wedding.",
             translation="Voy a asistir a la boda.",expected_source="wedding",expected_target="boda"),
        dict(id="noun-geometry-wedding-grammar-only",original="It is a wedding.",
             translation="Es una boda.",forbidden_source="wedding",forbidden_target="boda"),
        dict(id="noun-geometry-wedding-proper-name",original="I will attend Wedding.",
             translation="Voy a asistir a Boda.",forbidden_source="Wedding",forbidden_target="Boda"),
    ]
    for row in examples:
        row.update(dataset="authored-noun-geometry-behavior",source="en",target="es")
    # Put new regressions first so a partial native run exposes their outcome.
    cases=examples+cases
    manifest.update(cases=len(cases),datasets=dict(Counter(r["dataset"] for r in cases)),
        prior_manifest_sha256=sha(a.base/"manifest.json"),compiler_sha256=sha(Path(__file__)),
        noun_geometry_examples=examples,
        noun_geometry_limit="Author-designed regressions, not independent semantic acceptance.")
    a.output.mkdir(parents=True,exist_ok=False)
    for shard in manifest["shards"]:
        source=a.base/(shard["language"]+".sqlite")
        assert source.stat().st_size==shard["bytes"]
        (a.output/source.name).symlink_to(source.resolve())
    for name in ("diagnostic-receipt.json","evaluation-exclusions.sqlite","EVALUATION-NOTICE.txt","LICENSE-FLORES-200.txt"):
        if (a.base/name).exists():
            (a.output/name).symlink_to((a.base/name).resolve())
    path=a.output/"cases.json"
    path.write_text(json.dumps(cases,ensure_ascii=False,separators=(",",":"))+"\n")
    manifest["cases_sha256"]=sha(path)
    (a.output/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(dict(cases=len(cases),manifest_sha256=sha(a.output/"manifest.json"))))

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    main(p.parse_args())

